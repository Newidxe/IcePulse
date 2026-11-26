import sys
import subprocess
import os

required_libs = {"telethon": "telethon", "requests": "requests", "qrcode": "qrcode"}
for lib_name, pip_name in required_libs.items():
    try:
        __import__(lib_name)
    except ImportError:
        print(f"[!] Библиотека {lib_name} не найдена. Устанавливаем автоматически...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])

import asyncio
import hashlib
import platform
import random
import re
import sqlite3
import uuid
import requests
import time
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SlowModeWaitError, SessionPasswordNeededError
import qrcode

IMPORT_DIR = "Import_Bases"
if not os.path.exists(IMPORT_DIR):
    os.makedirs(IMPORT_DIR)

DB_FILE = "icepulse_data.db"
SESSION_FILE = "icepulse_session"

VERSION_URL = "https://raw.githubusercontent.com/Newidxe/IcePulse/main/version.txt"
SCRIPT_URL = "https://raw.githubusercontent.com/Newidxe/IcePulse/main/icepulse.py"

SUPABASE_URL = "https://xajjgerykmwmjxsacqiw.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_px2tcqcsBXy3l6g4cLZ5ow_rBZ6bIFE"

C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_ICE = "\033[96m"
C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_YELLOW = "\033[93m"
C_GRAY = "\033[90m"


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )""")
        c.execute("""CREATE TABLE IF NOT EXISTS targets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_entity TEXT,
                        topic_id INTEGER,
                        category TEXT DEFAULT 'Основная',
                        delay_sec INTEGER DEFAULT 900
                    )""")
        c.execute("""CREATE TABLE IF NOT EXISTS category_ads (
                        category TEXT PRIMARY KEY,
                        ad_mode TEXT,
                        ad_text TEXT,
                        ad_photo TEXT,
                        ad_source_chat TEXT,
                        ad_msg_id INTEGER,
                        ad_preview TEXT
                    )""")
        try:
            c.execute("ALTER TABLE targets ADD COLUMN category TEXT DEFAULT 'Основная'")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE targets ADD COLUMN delay_sec INTEGER DEFAULT 900")
        except Exception:
            pass
        conn.commit()


def get_setting(key: str, default=""):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = c.fetchone()
        return row[0] if row is not None else default


def set_setting(key: str, value: str):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()


def get_category_ad(category: str) -> dict | None:
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT ad_mode, ad_text, ad_photo, ad_source_chat, ad_msg_id, ad_preview FROM category_ads WHERE category = ?",
            (category,)
        )
        row = c.fetchone()
        if not row or not row[0]:
            return None
        return {
            "ad_mode": row[0],
            "ad_text": row[1] or "",
            "ad_photo": row[2] or "",
            "ad_source_chat": row[3] or "me",
            "ad_msg_id": int(row[4] or 0),
            "ad_preview": row[5] or ""
        }


def get_all_category_ads() -> dict[str, dict]:
    result = {}
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.cursor().execute(
            "SELECT category, ad_mode, ad_text, ad_photo, ad_source_chat, ad_msg_id, ad_preview FROM category_ads"
        ).fetchall()
    for cat, mode, txt, photo, src, msg_id, prev in rows:
        if mode:
            result[cat] = {
                "ad_mode": mode,
                "ad_text": txt or "",
                "ad_photo": photo or "",
                "ad_source_chat": src or "me",
                "ad_msg_id": int(msg_id or 0),
                "ad_preview": prev or ""
            }
    return result


def set_category_ad(category: str, ad_mode: str, ad_text="", ad_photo="", ad_source_chat="me", ad_msg_id=0, ad_preview=""):
    with sqlite3.connect(DB_FILE) as conn:
        conn.cursor().execute(
            """INSERT OR REPLACE INTO category_ads
               (category, ad_mode, ad_text, ad_photo, ad_source_chat, ad_msg_id, ad_preview)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (category, ad_mode, ad_text, ad_photo, str(ad_source_chat), int(ad_msg_id or 0), ad_preview)
        )
        conn.commit()


def delete_category_ad(category: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.cursor().execute("DELETE FROM category_ads WHERE category = ?", (category,))
        conn.commit()


def format_ad_label(ad_data: dict | None, fallback_label="Общий пост") -> str:
    if not ad_data or not ad_data.get("ad_mode"):
        return f"{C_GRAY}{fallback_label}{C_RESET}"
    if ad_data["ad_mode"] == "console":
        txt = ad_data.get("ad_text", "")
        photo = ad_data.get("ad_photo", "")
        short_txt = (txt[:30] + "...") if len(txt) > 30 else txt
        photo_str = " + Фото" if photo else ""
        return f"{C_GREEN}Текст: \"{short_txt}\"{photo_str}{C_RESET}"
    if ad_data["ad_mode"] == "saved":
        src = ad_data.get("ad_source_chat", "me") or "me"
        msg_id = ad_data.get("ad_msg_id", 0)
        preview = ad_data.get("ad_preview", "")
        src_label = "Избранное" if src == "me" else src
        prev_str = f" | \"{preview}\"" if preview else ""
        return f"{C_GREEN}Пост ({src_label}, ID: {msg_id}){prev_str}{C_RESET}"
    return f"{C_GRAY}{fallback_label}{C_RESET}"


def remove_tg_session_files():
    removed = True
    for sf in [f"{SESSION_FILE}.session", f"{SESSION_FILE}.session-journal"]:
        if os.path.exists(sf):
            try:
                os.remove(sf)
            except Exception:
                removed = False
    return removed


def reset_local_data():
    try:
        if os.path.exists(DB_FILE):
            try:
                os.remove(DB_FILE)
            except Exception:
                pass
        remove_tg_session_files()
        init_db()
        return True
    except Exception:
        return False


def check_for_updates():
    try:
        print("[*] Проверка обновлений...")
        local_version = get_setting("current_version", "1.0")

        response = requests.get(VERSION_URL, timeout=3)
        if response.status_code == 200:
            latest_version = response.text.strip()

            if latest_version != local_version:
                print(f"\n[!] Вышла новая версия {latest_version}, загружаем обновление...")

                script_response = requests.get(SCRIPT_URL, timeout=10)
                if script_response.status_code == 200:
                    new_code = script_response.text

                    with open("icepulse.py", "w", encoding="utf-8") as f:
                        f.write(new_code)

                    set_setting("current_version", latest_version)

                    print("[+] Обновление успешно установлено! Быстрый перезапуск...\n")
                    time.sleep(1)

                    subprocess.call([sys.executable] + sys.argv)
                    sys.exit(0)
            else:
                print(f"[+] У вас установлена актуальная версия IcePulse ({local_version}).")
    except Exception:
        print("[*] Автообновление пропущено (оффлайн режим).")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()


def get_hwid() -> str:
    raw_id = ""
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            )
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            raw_id = f"{guid}-{platform.processor()}"
        except Exception:
            raw_id = f"{uuid.getnode()}-{platform.node()}"
    else:
        raw_id = f"{uuid.getnode()}-{platform.node()}"

    digest = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16].upper()
    return f"HWID-{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"


USER_HWID = get_hwid()


def supabase_rpc(func_name: str, payload: dict) -> dict:
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/rpc/{func_name}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json"
    }
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    return r.json()


def register_profile_online(email: str, password: str) -> tuple[bool, str]:
    try:
        data = supabase_rpc("register_icepulse_user", {
            "p_email": email.strip().lower(),
            "p_pass_hash": hash_password(password),
            "p_hwid": USER_HWID
        })
        if data.get("ok"):
            return True, f"{C_GREEN}{data.get('msg')}{C_RESET}"
        return False, f"{C_RED}{data.get('msg', 'Ошибка регистрации.')}{C_RESET}"
    except Exception as e:
        return False, f"{C_RED}Ошибка связи с сервером: {e}{C_RESET}"


def check_profile_online(email: str, pass_hash: str) -> tuple[bool, bool, str]:
    try:
        data = supabase_rpc("login_icepulse_user", {
            "p_email": email.strip().lower(),
            "p_pass_hash": pass_hash,
            "p_hwid": USER_HWID
        })
        if not data.get("ok"):
            return False, False, f"{C_RED}{data.get('msg', 'Ошибка входа.')}{C_RESET}"

        if data.get("active"):
            rem = int(data.get("remaining_sec", 0))
            days = rem // 86400
            hours = (rem % 86400) // 3600
            mins = (rem % 3600) // 60
            exp_str = data.get("expires_str", "")
            return True, True, f"{C_GREEN}АКТИВНА ({days} дн. {hours} ч. {mins} мин. | до {exp_str}){C_RESET}"
        else:
            return True, False, f"{C_RED}НЕ АКТИВНА (Активируйте ключ в пункте [6]){C_RESET}"
    except Exception:
        return True, False, f"{C_YELLOW}Нет связи с сервером лицензий (проверьте интернет){C_RESET}"


def activate_key_online(email: str, pass_hash: str, key_code: str) -> tuple[bool, str]:
    try:
        data = supabase_rpc("activate_icepulse_key", {
            "p_email": email.strip().lower(),
            "p_pass_hash": pass_hash,
            "p_hwid": USER_HWID,
            "p_key": key_code.strip()
        })
        if data.get("ok"):
            return True, f"{C_GREEN}{data.get('msg')}{C_RESET}"
        return False, f"{C_RED}{data.get('msg', 'Ошибка активации.')}{C_RESET}"
    except Exception as e:
        return False, f"{C_RED}Ошибка соединения с сервером: {e}{C_RESET}"


async def ainput(prompt: str = "") -> str:
    return await asyncio.to_thread(input, prompt)


async def ensure_authenticated() -> tuple[str, str]:
    saved_email = get_setting("user_email", "")
    saved_hash = get_setting("user_pass_hash", "")

    if saved_email and saved_hash:
        print(f"{C_ICE}Проверка профиля {saved_email}...{C_RESET}")
        login_ok, _, status_msg = await asyncio.to_thread(check_profile_online, saved_email, saved_hash)
        if login_ok:
            return saved_email, saved_hash
        else:
            print(f"\n{status_msg}")
            set_setting("user_email", "")
            set_setting("user_pass_hash", "")
            await ainput(f"{C_GRAY}Нажмите Enter, чтобы войти заново...{C_RESET}")

    while True:
        clear_screen()
        print(f"{C_ICE}{C_BOLD}========================================================{C_RESET}")
        print(f"{C_ICE}{C_BOLD}         ICEPULSE - АВТОРИЗАЦИЯ ПРОФИЛЯ                 {C_RESET}")
        print(f"{C_ICE}{C_BOLD}========================================================{C_RESET}")
        print(f" Ваш HWID: {C_ICE}{USER_HWID}{C_RESET}\n")
        print(f" {C_ICE}{C_BOLD}[1]{C_RESET} Войти в существующий профиль     {C_GRAY}| Для уже зарегистрированных{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[2]{C_RESET} Создать новый профиль            {C_GRAY}| Регистрация и привязка HWID{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[3]{C_RESET} Сбросить привязку (Очистка кэша) {C_GRAY}| Удалить локальные данные{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[0]{C_RESET} Выход                            {C_GRAY}| Закрыть программу{C_RESET}")
        print(f"{C_ICE}{C_BOLD}========================================================{C_RESET}")

        choice = (await ainput(f"\n{C_BOLD}Выберите действие (0-3): {C_RESET}")).strip()

        if choice == "0":
            raise SystemExit()
        elif choice == "3":
            if reset_local_data():
                print(f"\n{C_GREEN}Локальные данные и привязки успешно сброшены!{C_RESET}")
            else:
                print(f"\n{C_YELLOW}Часть файлов занята процессами, но база пересоздана.{C_RESET}")
            await asyncio.sleep(1.5)
            continue
        elif choice == "1":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== ВХОД В ПРОФИЛЬ ICEPULSE ==={C_RESET}\n")
            email = (await ainput(f"Введите вашу почту (Email) {C_GRAY}[0 - Назад]{C_RESET}: ")).strip().lower()
            if email == "0":
                continue
            password = (await ainput(f"Введите ваш пароль {C_GRAY}[0 - Назад]{C_RESET}: ")).strip()
            if password == "0":
                continue

            if not email or not password:
                print(f"\n{C_RED}Почта и пароль не могут быть пустыми.{C_RESET}")
                await ainput(f"{C_GRAY}Нажмите Enter...{C_RESET}")
                continue

            p_hash = hash_password(password)
            print(f"\n{C_GRAY}Проверка данных на сервере...{C_RESET}")
            login_ok, _, msg = await asyncio.to_thread(check_profile_online, email, p_hash)

            if login_ok:
                set_setting("user_email", email)
                set_setting("user_pass_hash", p_hash)
                print(f"\n{C_GREEN}Успешный вход в профиль {email}!{C_RESET}")
                await asyncio.sleep(1)
                return email, p_hash
            else:
                print(f"\n{msg}")
                await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
        elif choice == "2":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== СОЗДАНИЕ ПРОФИЛЯ ICEPULSE ==={C_RESET}")
            email = (await ainput(f"Введите вашу почту {C_GRAY}[0 - Назад]{C_RESET}: ")).strip().lower()
            if email == "0":
                continue
            password = (await ainput(f"Придумайте пароль (мин. 4 символа) {C_GRAY}[0 - Назад]{C_RESET}: ")).strip()
            if password == "0":
                continue

            if "@" not in email or "." not in email:
                print(f"\n{C_RED}Укажите корректный адрес почты.{C_RESET}")
                await ainput(f"{C_GRAY}Нажмите Enter...{C_RESET}")
                continue
            if len(password) < 4:
                print(f"\n{C_RED}Пароль должен быть не короче 4 символов.{C_RESET}")
                await ainput(f"{C_GRAY}Нажмите Enter...{C_RESET}")
                continue

            print(f"\n{C_GRAY}Создание профиля на сервере...{C_RESET}")
            ok, msg = await asyncio.to_thread(register_profile_online, email, password)
            print(f"\n{msg}")

            if ok:
                p_hash = hash_password(password)
                set_setting("user_email", email)
                set_setting("user_pass_hash", p_hash)
                await asyncio.sleep(1.5)
                return email, p_hash
            else:
                await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")


def parse_single_target(raw: str) -> tuple[str | None, int | None]:
    raw = raw.strip()
    if not raw:
        return None, None

    m_priv = re.search(r"t\.me/c/(\d+)(?:/(\d+))?", raw)
    if m_priv:
        return f"-100{m_priv.group(1)}", int(m_priv.group(2)) if m_priv.group(2) else None

    m_pub = re.search(r"t\.me/([a-zA-Z0-9_]+)(?:/(\d+))?", raw)
    if m_pub:
        return m_pub.group(1), int(m_pub.group(2)) if m_pub.group(2) else None

    return raw.lstrip("@"), None


def parse_post_reference(raw: str) -> tuple[str | None, int | None]:
    raw = raw.strip()
    if not raw:
        return None, None

    if raw.isdigit():
        return "me", int(raw)

    m_priv = re.search(r"t\.me/c/(\d+)/(?:\d+/)?(\d+)", raw)
    if m_priv:
        return f"-100{m_priv.group(1)}", int(m_priv.group(2))

    m_pub = re.search(r"t\.me/([a-zA-Z0-9_]+)/(?:\d+/)?(\d+)", raw)
    if m_pub:
        return m_pub.group(1), int(m_pub.group(2))

    return None, None


def format_msg_preview(msg) -> str:
    txt = (msg.raw_text or "").replace("\n", " ").strip()
    if txt:
        return (txt[:40] + "...") if len(txt) > 40 else txt
    if msg.photo:
        return "[Фото без текста]"
    if msg.video:
        return "[Видео без текста]"
    if msg.document:
        return "[Файл / Медиа]"
    return "[Пустое сообщение]"


async def configure_ad_interactive(client: TelegramClient, target_category: str | None = None):
    clear_screen()
    scope_title = f"ДЛЯ КАТЕГОРИИ '{target_category}'" if target_category else "ОБЩИЙ (ПО УМОЛЧАНИЮ)"
    print(f"{C_ICE}{C_BOLD}=== НАСТРОЙКА ПОСТА: {scope_title} ==={C_RESET}\n")
    print(f" {C_BOLD}[1]{C_RESET} Задать свой текст / фото           {C_GRAY}| Ввод текста прямо в консоли{C_RESET}")
    print(f" {C_BOLD}[2]{C_RESET} Указать пост по ссылке или ID      {C_GRAY}| Ссылка t.me/.../123 или ID из Избранного{C_RESET}")
    print(f" {C_BOLD}[3]{C_RESET} Взять последний пост из Избранного {C_GRAY}| Последнее сообщение в 'Избранное'{C_RESET}")
    sub = (await ainput(f"\n{C_BOLD}Ваш выбор {C_GRAY}(1-3 | 0 - Назад):{C_RESET} ")).strip()

    if sub == "0" or sub not in ["1", "2", "3"]:
        return

    if sub == "1":
        text_val = (await ainput(f"\n{C_BOLD}Введите рекламный текст{C_RESET} {C_GRAY}[0 - Отмена]{C_RESET}:{C_BOLD}\n-> {C_RESET}")).strip()
        if text_val == "0" or not text_val:
            return

        photo_val = (await ainput(f"{C_BOLD}Путь к фото{C_RESET} {C_GRAY}(Enter - без фото, 0 - Отмена):{C_RESET} ")).strip().strip('"')
        if photo_val == "0":
            return

        valid_photo = photo_val if os.path.isfile(photo_val) else ""
        if target_category:
            set_category_ad(target_category, "console", ad_text=text_val, ad_photo=valid_photo)
        else:
            set_setting("ad_mode", "console")
            set_setting("ad_text", text_val)
            set_setting("ad_photo", valid_photo)
        print(f"\n{C_GREEN}Объявление успешно сохранено!{C_RESET}")

    elif sub == "2":
        raw_ref = (await ainput(f"\n{C_BOLD}Вставьте ссылку на пост (t.me/...) или ID из Избранного {C_GRAY}[0 - Отмена]{C_RESET}:\n-> ")).strip()
        if raw_ref == "0":
            return

        src_chat, msg_id = parse_post_reference(raw_ref)
        if not src_chat or not msg_id:
            print(f"\n{C_RED}[!] Не удалось распознать ссылку или ID сообщения.{C_RESET}")
        else:
            try:
                src_entity = int(src_chat) if src_chat.lstrip("-").isdigit() else src_chat
                found_msg = await client.get_messages(src_entity, ids=msg_id)
                if found_msg:
                    prev = format_msg_preview(found_msg)
                    if target_category:
                        set_category_ad(
                            target_category,
                            "saved",
                            ad_source_chat=str(src_chat),
                            ad_msg_id=found_msg.id,
                            ad_preview=prev
                        )
                    else:
                        set_setting("ad_mode", "saved")
                        set_setting("ad_source_chat", str(src_chat))
                        set_setting("ad_msg_id", str(found_msg.id))
                        set_setting("ad_preview", prev)
                    print(f"\n{C_GREEN}Пост успешно найден и сохранён: \"{prev}\"{C_RESET}")
                else:
                    print(f"\n{C_RED}[!] Сообщение с таким ID не найдено.{C_RESET}")
            except Exception as e:
                print(f"\n{C_RED}[!] Ошибка доступа к посту: {e}{C_RESET}")

    elif sub == "3":
        msgs = await client.get_messages("me", limit=1)
        if msgs:
            prev = format_msg_preview(msgs[0])
            if target_category:
                set_category_ad(
                    target_category,
                    "saved",
                    ad_source_chat="me",
                    ad_msg_id=msgs[0].id,
                    ad_preview=prev
                )
            else:
                set_setting("ad_mode", "saved")
                set_setting("ad_source_chat", "me")
                set_setting("ad_msg_id", str(msgs[0].id))
                set_setting("ad_preview", prev)
            print(f"\n{C_GREEN}Последний пост из Избранного захвачен: \"{prev}\"{C_RESET}")
        else:
            print(f"\n{C_RED}[!] У вас пусто в 'Избранном'. Перешлите туда пост и попробуйте снова.{C_RESET}")

    await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")


async def mailing_loop(client: TelegramClient, stop_event: asyncio.Event, email: str, pass_hash: str):
    next_run_times = {}

    while not stop_event.is_set():
        login_ok, is_active, status_msg = await asyncio.to_thread(check_profile_online, email, pass_hash)
        if (not login_ok or not is_active) and "Нет связи" not in status_msg:
            print(f"\n{C_RED}[!] Подписка профиля неактивна! Рассылка остановлена.{C_RESET}")
            stop_event.set()
            break

        global_ad = {
            "ad_mode": get_setting("ad_mode", ""),
            "ad_text": get_setting("ad_text", ""),
            "ad_photo": get_setting("ad_photo", ""),
            "ad_source_chat": get_setting("ad_source_chat", "me") or "me",
            "ad_msg_id": int(get_setting("ad_msg_id", "0") or 0)
        }
        cat_ads = get_all_category_ads()
        saved_msg_cache = {}

        with sqlite3.connect(DB_FILE) as conn:
            targets = conn.cursor().execute("SELECT id, chat_entity, topic_id, category, delay_sec FROM targets").fetchall()

        sent_in_this_pass = False
        now_ts = time.time()

        for r_id, chat_entity, topic_id, category, delay_sec in targets:
            if stop_event.is_set():
                break

            if now_ts >= next_run_times.get(r_id, 0):
                now_str = datetime.now().strftime("%H:%M:%S")
                ad_cfg = cat_ads.get(category) or global_ad

                if not ad_cfg.get("ad_mode"):
                    print(f"{C_GRAY}[{now_str}]{C_RESET} {C_YELLOW}[Пропуск]{C_RESET} Для категории '{category}' не задан рекламный пост.")
                    next_run_times[r_id] = time.time() + delay_sec
                    continue

                saved_msg_obj = None
                if ad_cfg["ad_mode"] == "saved":
                    cache_key = (ad_cfg["ad_source_chat"], ad_cfg["ad_msg_id"])
                    if cache_key not in saved_msg_cache:
                        src_chat = ad_cfg["ad_source_chat"]
                        src_entity = int(src_chat) if src_chat.lstrip("-").isdigit() else src_chat
                        try:
                            saved_msg_cache[cache_key] = await client.get_messages(src_entity, ids=ad_cfg["ad_msg_id"])
                        except Exception as e:
                            print(f"{C_GRAY}[{now_str}]{C_RESET} {C_RED}[!] Ошибка загрузки поста ({src_chat}/{ad_cfg['ad_msg_id']}): {e}{C_RESET}")
                            saved_msg_cache[cache_key] = None
                    saved_msg_obj = saved_msg_cache[cache_key]
                    if not saved_msg_obj:
                        print(f"{C_GRAY}[{now_str}]{C_RESET} {C_RED}[!] Пост (ID: {ad_cfg['ad_msg_id']}) для категории '{category}' не найден.{C_RESET}")
                        next_run_times[r_id] = time.time() + delay_sec
                        continue

                entity = int(chat_entity) if chat_entity.lstrip("-").isdigit() else chat_entity
                topic_label = f" (Ветка: {topic_id})" if topic_id else ""

                try:
                    if ad_cfg["ad_mode"] == "saved" and saved_msg_obj:
                        await client.send_message(entity=entity, message=saved_msg_obj, reply_to=topic_id)
                    else:
                        ad_photo = ad_cfg.get("ad_photo", "")
                        file_to_send = ad_photo if (ad_photo and os.path.isfile(ad_photo)) else None
                        await client.send_message(entity=entity, message=ad_cfg["ad_text"], file=file_to_send, reply_to=topic_id)

                    print(f"{C_GRAY}[{now_str}]{C_RESET} {C_ICE}[Кат: {category} | {delay_sec//60}мин]{C_RESET} {C_GREEN}Отправлено:{C_RESET} {chat_entity}{topic_label}")
                except SlowModeWaitError as e:
                    print(f"{C_GRAY}[{now_str}]{C_RESET} {C_YELLOW}[Медленный режим]{C_RESET} {chat_entity}: ждём {e.seconds} сек.")
                except FloodWaitError as e:
                    print(f"{C_GRAY}[{now_str}]{C_RESET} {C_RED}[!] FloodWait: общая пауза {e.seconds} сек.{C_RESET}")
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=e.seconds + 5)
                    except asyncio.TimeoutError:
                        pass
                except Exception as e:
                    print(f"{C_GRAY}[{now_str}]{C_RESET} {C_RED}[-] Ошибка в {chat_entity}: {e}{C_RESET}")

                next_run_times[r_id] = time.time() + delay_sec + random.randint(10, 25)
                sent_in_this_pass = True

                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=random.randint(4, 8))
                except asyncio.TimeoutError:
                    pass

        if not sent_in_this_pass and not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass


def get_ad_summary() -> str:
    global_ad = {
        "ad_mode": get_setting("ad_mode", ""),
        "ad_text": get_setting("ad_text", ""),
        "ad_photo": get_setting("ad_photo", ""),
        "ad_source_chat": get_setting("ad_source_chat", "me") or "me",
        "ad_msg_id": int(get_setting("ad_msg_id", "0") or 0),
        "ad_preview": get_setting("ad_preview", "")
    }
    with sqlite3.connect(DB_FILE) as conn:
        active_cats = {row[0] for row in conn.cursor().execute("SELECT DISTINCT category FROM targets").fetchall()}
    custom_ads = {k: v for k, v in get_all_category_ads().items() if k in active_cats}

    base_str = format_ad_label(global_ad, fallback_label="")
    if not global_ad["ad_mode"]:
        base_str = f"{C_RED}Общий не задан{C_RESET}"

    if custom_ads:
        return f"{base_str} {C_ICE}(+ отд. постов для категорий: {len(custom_ads)}){C_RESET}"
    return base_str


async def console_menu(client: TelegramClient, email: str, pass_hash: str):
    me = await client.get_me()
    tg_account = f"{me.first_name or ''} (@{me.username})" if me.username else f"{me.first_name or ''} (ID: {me.id})"

    while True:
        clear_screen()
        _, is_active, lic_status_str = await asyncio.to_thread(check_profile_online, email, pass_hash)

        with sqlite3.connect(DB_FILE) as conn:
            chats_count = conn.cursor().execute("SELECT COUNT(*) FROM targets").fetchone()[0]

        print(f"{C_ICE}{C_BOLD}======================================================================{C_RESET}")
        print(f"{C_ICE}{C_BOLD}                 ICEPULSE | TELEGRAM AUTO-POSTER                      {C_RESET}")
        print(f"{C_ICE}{C_BOLD}======================================================================{C_RESET}")
        print(f" Профиль:         {C_BOLD}{email}{C_RESET}")
        print(f" Аккаунт TG:      {C_BOLD}{tg_account}{C_RESET}")
        print(f" Лицензия:        {lic_status_str}")
        print(f" Рекламный пост:  {get_ad_summary()}")
        print(f" Чатов в базе:    {C_BOLD}{chats_count} шт.{C_RESET}")
        print(f"{C_BLUE}----------------------------------------------------------------------{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[1]{C_RESET} Запустить авторассылку IcePulse       {C_GRAY}| Старт отправки сообщений{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[2]{C_RESET} Задать рекламный текст / пост         {C_GRAY}| Общий или отдельно для категории{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[3]{C_RESET} Добавить чаты и категории (TXT/Руки)  {C_GRAY}| Импорт баз с разной задержкой{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[4]{C_RESET} Список чатов базы / Удалить чаты      {C_GRAY}| Управление добавленными чатами{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[5]{C_RESET} Управление категориями и таймерами    {C_GRAY}| Таймеры и отдельные посты папок{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[6]{C_RESET} Активировать / продлить ключ IcePulse {C_GRAY}| Управление подпиской{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[7]{C_RESET} Сменить Telegram аккаунт / API        {C_GRAY}| Быстрая замена при спамблоке{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[8]{C_RESET} Выйти из профиля IcePulse             {C_GRAY}| Сменить почту / лицензию{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[0]{C_RESET} Выход из программы                    {C_GRAY}| Закрыть софт{C_RESET}")
        print(f"{C_ICE}{C_BOLD}======================================================================{C_RESET}")

        choice = (await ainput(f"\n{C_BOLD}Выберите пункт меню (0-8): {C_RESET}")).strip()

        if choice == "6":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== АКТИВАЦИЯ КЛЮЧА ==={C_RESET}")
            key_str = (await ainput(f"Введите ваш ключ {C_GRAY}[0 - Отмена]:{C_RESET} ")).strip()
            if key_str == "0":
                continue

            _, msg = await asyncio.to_thread(activate_key_online, email, pass_hash, key_str)
            print(f"\n{msg}")
            await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
            continue

        if choice == "7":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== СМЕНА TELEGRAM АККАУНТА И API ==={C_RESET}\n")
            print(f"{C_GRAY}База чатов, категории, задержки и профиль IcePulse сохранятся.{C_RESET}\n")
            print(f" {C_ICE}{C_BOLD}[1]{C_RESET} Сменить только Telegram аккаунт       {C_GRAY}| Очистить сессию (API останется){C_RESET}")
            print(f" {C_ICE}{C_BOLD}[2]{C_RESET} Сменить Telegram аккаунт + API ключи  {C_GRAY}| Очистить сессию, API_ID и API_HASH{C_RESET}")
            print(f" {C_ICE}{C_BOLD}[0]{C_RESET} Назад")

            sub = (await ainput(f"\n{C_BOLD}Ваш выбор (0-2): {C_RESET}")).strip()
            if sub == "0" or sub not in ["1", "2"]:
                continue

            print(f"\n{C_YELLOW}Отключение текущего аккаунта Telegram...{C_RESET}")
            try:
                await client.disconnect()
            except Exception:
                pass

            remove_tg_session_files()

            if sub == "2":
                set_setting("api_id", "")
                set_setting("api_hash", "")
                print(f"{C_GREEN}Сессия Telegram и API ключи очищены! Перезапуск для нового входа...{C_RESET}")
            else:
                print(f"{C_GREEN}Сессия Telegram очищена! Перезапуск для входа в новый аккаунт...{C_RESET}")

            await asyncio.sleep(1.5)
            subprocess.call([sys.executable] + sys.argv)
            sys.exit(0)

        if choice == "8":
            clear_screen()
            confirm = (await ainput(f"{C_YELLOW}Выйти из профиля IcePulse ({email})?{C_RESET} {C_GRAY}(1 - Да, 0 - Отмена):{C_RESET} ")).strip()
            if confirm != "1":
                continue
            set_setting("user_email", "")
            set_setting("user_pass_hash", "")
            email, pass_hash = await ensure_authenticated()
            continue

        if choice == "0":
            break

        if not is_active:
            print(f"\n{C_RED}Доступ закрыт! Сначала активируйте ключ в пункте [6].{C_RESET}")
            await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
            continue

        if choice == "1":
            has_global_ad = bool(get_setting("ad_mode"))
            has_cat_ads = bool(get_all_category_ads())
            if not has_global_ad and not has_cat_ads:
                print(f"\n{C_YELLOW}Сначала задайте рекламный пост в пункте [2]!{C_RESET}")
                await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
                continue
            if chats_count == 0:
                print(f"\n{C_YELLOW}Сначала добавьте хотя бы один чат в пункте [3]!{C_RESET}")
                await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
                continue

            clear_screen()
            print(f"{C_ICE}ICEPULSE АКТИВЕН. Независимые таймеры по категориям запущены.{C_RESET}")
            print(f"{C_GRAY}Нажмите Enter для остановки рассылки.{C_RESET}\n")

            stop_event = asyncio.Event()
            task = asyncio.create_task(mailing_loop(client, stop_event, email, pass_hash))
            await ainput()
            stop_event.set()
            await task
            print(f"\n{C_YELLOW}Рассылка остановлена.{C_RESET}")
            await asyncio.sleep(1)

        elif choice == "2":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== НАСТРОЙКА РЕКЛАМНОГО ПОСТА ==={C_RESET}\n")
            print(f" {C_BOLD}[1]{C_RESET} Общий пост (по умолчанию)         {C_GRAY}| Для всех категорий без своего поста{C_RESET}")
            print(f" {C_BOLD}[2]{C_RESET} Отдельный пост для категории      {C_GRAY}| Выбрать папку чатов и задать ей свой пост{C_RESET}")
            print(f" {C_BOLD}[3]{C_RESET} Сбросить отдельный пост категории {C_GRAY}| Вернуть категорию на общий пост{C_RESET}")
            scope = (await ainput(f"\n{C_BOLD}Ваш выбор {C_GRAY}(1-3 | 0 - Назад):{C_RESET} ")).strip()

            if scope == "0":
                continue

            if scope == "1":
                await configure_ad_interactive(client, target_category=None)

            elif scope in ["2", "3"]:
                with sqlite3.connect(DB_FILE) as conn:
                    cat_rows = conn.cursor().execute("SELECT DISTINCT category FROM targets ORDER BY category").fetchall()
                cats = [r[0] for r in cat_rows]

                if not cats:
                    print(f"\n{C_YELLOW}В базе пока нет ни одной категории. Сначала добавьте чаты в пункте [3].{C_RESET}")
                    await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
                    continue

                clear_screen()
                title = "ВЫБЕРИТЕ КАТЕГОРИЮ ДЛЯ ОТДЕЛЬНОГО ПОСТА" if scope == "2" else "ВЫБЕРИТЕ КАТЕГОРИЮ ДЛЯ СБРОСА ПОСТА"
                print(f"{C_ICE}{C_BOLD}=== {title} ==={C_RESET}\n")
                for i, cat in enumerate(cats, 1):
                    c_ad = get_category_ad(cat)
                    print(f" [{i}] {C_ICE}{cat}{C_RESET} | {format_ad_label(c_ad)}")

                pick = (await ainput(f"\n{C_BOLD}Номер категории {C_GRAY}[0 - Назад]:{C_RESET} ")).strip()
                if pick == "0" or not pick.isdigit() or not (1 <= int(pick) <= len(cats)):
                    continue

                chosen_cat = cats[int(pick) - 1]
                if scope == "2":
                    await configure_ad_interactive(client, target_category=chosen_cat)
                else:
                    delete_category_ad(chosen_cat)
                    print(f"\n{C_GREEN}Для категории '{chosen_cat}' снова используется общий пост.{C_RESET}")
                    await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")

        elif choice == "3":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== ДОБАВЛЕНИЕ ЧАТОВ В БАЗУ ==={C_RESET}\n")
            print(f" {C_ICE}[1]{C_RESET} Добавить один чат вручную         {C_GRAY}| Вставить ссылку или @username{C_RESET}")
            print(f" {C_ICE}[2]{C_RESET} Импорт базы чатов из файла .TXT   {C_GRAY}| Авто-выбор файлов из папки '{IMPORT_DIR}'{C_RESET}")
            sub = (await ainput(f"\n{C_BOLD}Ваш выбор {C_GRAY}(1-2 | 0 - Назад):{C_RESET} ")).strip()

            if sub == "0":
                continue

            targets_to_add = []
            if sub == "1":
                raw = (await ainput(f"\n{C_BOLD}Вставьте ссылку или @username:{C_RESET} {C_GRAY}[0 - Отмена]{C_RESET}\n-> ")).strip()
                if raw == "0":
                    continue
                c, t = parse_single_target(raw)
                if c:
                    targets_to_add.append((c, t))
            elif sub == "2":
                txt_files = [f for f in os.listdir(IMPORT_DIR) if f.endswith('.txt')]
                if not txt_files:
                    print(f"\n{C_YELLOW}[!] В папке '{IMPORT_DIR}' нет текстовых файлов.{C_RESET}")
                    print(f"{C_GRAY}Закиньте туда .txt файлы с чатами и возвращайтесь.{C_RESET}")
                else:
                    print(f"\n{C_ICE}Доступные TXT базы в папке '{IMPORT_DIR}':{C_RESET}")
                    for i, file_name in enumerate(txt_files, 1):
                        print(f" {C_BOLD}[{i}]{C_RESET} {file_name}")

                    f_choice = (await ainput(f"\n{C_BOLD}Введите номер нужного файла {C_GRAY}[0 - Отмена]{C_RESET}: ")).strip()
                    if f_choice == "0":
                        continue

                    if f_choice.isdigit() and 1 <= int(f_choice) <= len(txt_files):
                        selected_file = txt_files[int(f_choice) - 1]
                        filepath = os.path.join(IMPORT_DIR, selected_file)

                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()

                        items = re.split(r'[\s\n]+', content.strip())
                        for item in items:
                            c, t = parse_single_target(item)
                            if c:
                                targets_to_add.append((c, t))
                        print(f"\n{C_GREEN}База '{selected_file}' прочитана! Найдено чатов: {len(targets_to_add)}{C_RESET}")
                    else:
                        print(f"\n{C_RED}[!] Неверный выбор.{C_RESET}")

            if targets_to_add:
                print(f"\n{C_ICE}--- НАСТРОЙКА КАТЕГОРИИ И ЗАДЕРЖКИ ---{C_RESET}")
                cat = (await ainput(f"{C_BOLD}Введите название категории{C_RESET} {C_GRAY}(Enter - 'Основная', 0 - Отмена):{C_RESET} ")).strip()
                if cat == "0":
                    continue
                if not cat:
                    cat = "Основная"

                delay_m = (await ainput(f"{C_BOLD}Интервал рассылки для этой категории (в минутах){C_RESET} {C_GRAY}(Enter - 15 мин, 0 - Отмена):{C_RESET} ")).strip()
                if delay_m == "0":
                    continue

                delay_s = int(delay_m) * 60 if delay_m.isdigit() and int(delay_m) > 0 else 900

                with sqlite3.connect(DB_FILE) as conn:
                    for c, t in targets_to_add:
                        conn.cursor().execute(
                            "INSERT INTO targets (chat_entity, topic_id, category, delay_sec) VALUES (?, ?, ?, ?)",
                            (c, t, cat, delay_s)
                        )
                    conn.commit()
                print(f"\n{C_GREEN}Успешно добавлено {len(targets_to_add)} чат(ов) в категорию '{cat}' с задержкой {delay_s // 60} мин.!{C_RESET}")

            await ainput(f"\n{C_GRAY}Нажмите Enter для возврата...{C_RESET}")

        elif choice == "4":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== СПИСОК ДОБАВЛЕННЫХ ЧАТОВ ==={C_RESET}\n")
            with sqlite3.connect(DB_FILE) as conn:
                rows = conn.cursor().execute("SELECT id, chat_entity, topic_id, category, delay_sec FROM targets").fetchall()

            if not rows:
                print(f"{C_YELLOW}База чатов пуста.{C_RESET}")
            else:
                for r_id, c_ent, t_id, cat, d_sec in rows:
                    t_str = f" (Ветка: {t_id})" if t_id else ""
                    print(f"[{C_BOLD}ID: {r_id}{C_RESET}] {c_ent}{t_str} | Кат: {C_ICE}{cat}{C_RESET} | Задержка: {d_sec // 60} мин.")

            print(f"\n{C_GRAY}Подсказка: Введите 'all' чтобы очистить всю базу разом.{C_RESET}")
            del_id = (await ainput(f"{C_BOLD}Введите ID для удаления{C_RESET} {C_GRAY}(Enter или 0 - Назад):{C_RESET} ")).strip().lower()

            if del_id in ["0", ""]:
                continue

            if del_id == 'all':
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("DELETE FROM targets")
                    conn.cursor().execute("DELETE FROM category_ads")
                    conn.commit()
                print(f"\n{C_GREEN}Вся база чатов успешно очищена.{C_RESET}")
            elif del_id.isdigit():
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("DELETE FROM targets WHERE id = ?", (int(del_id),))
                    conn.commit()
                print(f"\n{C_GREEN}Чат успешно удален.{C_RESET}")
            await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")

        elif choice == "5":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== УПРАВЛЕНИЕ КАТЕГОРИЯМИ, ТАЙМЕРАМИ И ПОСТАМИ ==={C_RESET}\n")

            with sqlite3.connect(DB_FILE) as conn:
                categories = conn.cursor().execute(
                    "SELECT category, MIN(delay_sec), COUNT(*) FROM targets GROUP BY category ORDER BY category"
                ).fetchall()

            if not categories:
                print(f"{C_YELLOW}В базе пока нет ни одной категории с чатами.{C_RESET}")
                await ainput(f"\n{C_GRAY}Нажмите Enter для возврата...{C_RESET}")
                continue

            print(f" {C_BOLD}Текущие категории (папки) в базе:{C_RESET}")
            for i, (cat, d_sec, cnt) in enumerate(categories, 1):
                c_ad = get_category_ad(cat)
                print(f" [{i}] {C_ICE}{cat}{C_RESET} ({cnt} шт.) | {C_BOLD}{d_sec // 60} мин.{C_RESET} | Пост: {format_ad_label(c_ad)}")

            cat_choice = (await ainput(f"\nВведите номер категории для настройки {C_GRAY}[0 - Назад]:{C_RESET} ")).strip()
            if cat_choice == "0" or not cat_choice:
                continue

            if cat_choice.isdigit() and 1 <= int(cat_choice) <= len(categories):
                target_cat = categories[int(cat_choice) - 1][0]
                clear_screen()
                print(f"{C_ICE}{C_BOLD}=== КАТЕГОРИЯ: {target_cat} ==={C_RESET}\n")
                print(f" Текущий пост: {format_ad_label(get_category_ad(target_cat))}\n")
                print(f" {C_BOLD}[1]{C_RESET} Изменить интервал рассылки (таймер)")
                print(f" {C_BOLD}[2]{C_RESET} Задать отдельный рекламный пост")
                print(f" {C_BOLD}[3]{C_RESET} Сбросить пост на общий")
                print(f" {C_BOLD}[0]{C_RESET} Назад")

                act = (await ainput(f"\n{C_BOLD}Ваш выбор (0-3): {C_RESET}")).strip()
                if act == "1":
                    new_m = (await ainput(f"\nВведите новый интервал в минутах для '{target_cat}' {C_GRAY}[0 - Отмена]:{C_RESET} ")).strip()
                    if new_m == "0":
                        continue
                    if new_m.isdigit() and int(new_m) > 0:
                        with sqlite3.connect(DB_FILE) as conn:
                            conn.cursor().execute("UPDATE targets SET delay_sec = ? WHERE category = ?", (int(new_m) * 60, target_cat))
                            conn.commit()
                        print(f"\n{C_GREEN}Задержка для категории '{target_cat}' обновлена на {new_m} мин.!{C_RESET}")
                    else:
                        print(f"\n{C_RED}[!] Неверное значение минут.{C_RESET}")
                    await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
                elif act == "2":
                    await configure_ad_interactive(client, target_category=target_cat)
                elif act == "3":
                    delete_category_ad(target_cat)
                    print(f"\n{C_GREEN}Для категории '{target_cat}' снова используется общий пост.{C_RESET}")
                    await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
            else:
                print(f"\n{C_RED}[!] Неверный выбор категории.{C_RESET}")
                await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")


async def main():
    email, pass_hash = await ensure_authenticated()

    api_id = get_setting("api_id", "").strip()
    api_hash = get_setting("api_hash", "").strip()

    while not api_id.isdigit() or not api_hash:
        if api_id and not api_id.isdigit():
            print(f"\n{C_RED}[!] Сохранённый API_ID некорректен (должны быть только цифры). Введите заново.{C_RESET}")
            set_setting("api_id", "")
            set_setting("api_hash", "")
            await asyncio.sleep(1.5)

        clear_screen()
        print(f"{C_ICE}{C_BOLD}=== ПЕРВИЧНАЯ НАСТРОЙКА TELEGRAM API ==={C_RESET}")
        print(f"{C_GRAY}Ключи получаются один раз на официальном сайте: https://my.telegram.org{C_RESET}")
        print(f"{C_YELLOW}Внимание: сюда вводится НЕ ключ лицензии, а API_ID (цифры) и API_HASH!{C_RESET}\n")
        api_id = (await ainput("Введите ваш API_ID (только цифры): ")).strip()
        api_hash = (await ainput("Введите ваш API_HASH: ")).strip()

        if not api_id.isdigit() or not api_hash:
            print(f"\n{C_RED}[!] API_ID должен состоять только из цифр, а API_HASH не может быть пустым.{C_RESET}")
            await ainput(f"{C_GRAY}Нажмите Enter, чтобы попробовать снова...{C_RESET}")
            continue

        set_setting("api_id", api_id)
        set_setting("api_hash", api_hash)

    client = TelegramClient(
        SESSION_FILE,
        int(api_id),
        api_hash,
        device_model="Desktop PC",
        system_version="Windows 11 Pro",
        app_version="4.16.8 x64",
        lang_code="ru"
    )

    print(f"\n{C_ICE}Подключение IcePulse к серверам Telegram...{C_RESET}")
    await client.connect()

    if not await client.is_user_authorized():
        clear_screen()
        print(f"{C_ICE}{C_BOLD}=== АВТОРИЗАЦИЯ TELEGRAM ЧЕРЕЗ QR-КОД ==={C_RESET}")
        print(f"{C_YELLOW}Откройте Telegram на телефоне -> Настройки -> Устройства -> Подключить устройство{C_RESET}\n")

        try:
            qr = await client.qr_login()
            while not await client.is_user_authorized():
                qr_term = qrcode.QRCode()
                qr_term.add_data(qr.url)
                qr_term.make(fit=True)

                print(f"\n{C_BOLD}Отсканируйте этот QR-код камерой телефона:{C_RESET}")
                qr_term.print_ascii(invert=True)

                print(f"\n{C_GRAY}(Ожидание сканирования... Обновление QR-кода через 15 секунд){C_RESET}")
                try:
                    await qr.wait(15)
                except asyncio.TimeoutError:
                    qr = await client.recreate_qr()
                    clear_screen()
                    print(f"{C_YELLOW}[!] Срок старого QR-кода истек, сканируйте новый:{C_RESET}")

            print(f"\n{C_GREEN}Успешная авторизация в Telegram через QR-код!{C_RESET}")

        except SessionPasswordNeededError:
            print(f"\n{C_YELLOW}[!] На аккаунте включена двухэтапная аутентификация (Облачный пароль).{C_RESET}")
            password = await ainput(f"Введите пароль от аккаунта Telegram {C_GRAY}[0 - Отмена]{C_RESET}: ")
            if password.strip() == "0":
                sys.exit(0)
            await client.sign_in(password=password.strip())
            print(f"\n{C_GREEN}Успешный вход по облачному паролю!{C_RESET}")

        except Exception as e:
            print(f"\n{C_RED}Возникла ошибка при входе по QR-коду: {e}{C_RESET}")
            phone = await ainput(f"\n{C_BOLD}Давайте войдем по номеру.{C_RESET} Введите номер телефона (+380...) {C_GRAY}[0 - Отмена]{C_RESET}: ")
            if phone.strip() == "0":
                sys.exit(0)
            await client.send_code_request(phone.strip())
            code = await ainput(f"Введите код подтверждения из Telegram {C_GRAY}[0 - Отмена]{C_RESET}: ")
            if code.strip() == "0":
                sys.exit(0)
            await client.sign_in(phone.strip(), code.strip())
            print(f"\n{C_GREEN}Успешно авторизовано!{C_RESET}")

    await console_menu(client, email, pass_hash)
    await client.disconnect()


if __name__ == "__main__":
    os.system("")
    if os.name == "nt":
        os.system("title IcePulse - Telegram Auto-Poster")

    init_db()
    check_for_updates()

    try:
        asyncio.run(main())
    except Exception:
        import traceback
        print("\nКритическая ошибка:")
        traceback.print_exc()
    finally:
        input("\nНажмите Enter для выхода...")
