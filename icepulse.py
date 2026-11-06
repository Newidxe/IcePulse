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

# === НАСТРОЙКИ И ПУТИ ===
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

# === БАЗА ДАННЫХ И НАСТРОЙКИ ===
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

def reset_local_data():
    try:
        if os.path.exists(DB_FILE):
            try:
                os.remove(DB_FILE)
            except Exception:
                pass
                
        for sf in [f"{SESSION_FILE}.session", f"{SESSION_FILE}.session-journal"]:
            if os.path.exists(sf):
                try:
                    os.remove(sf)
                except Exception:
                    pass
                    
        init_db()
        return True
    except Exception:
        return False

# === СИСТЕМА УМНОГО АВТООБНОВЛЕНИЯ ===
def check_for_updates():
    try:
        print("[*] Проверка обновлений...")
        # Берем текущую версию из базы клиента (по умолчанию 1.0)
        local_version = get_setting("current_version", "1.0")
        
        response = requests.get(VERSION_URL, timeout=3)
        if response.status_code == 200:
            latest_version = response.text.strip()
            
            # Если версия на GitHub отличается от версии в базе клиента
            if latest_version != local_version:
                print(f"\n[!] Вышла новая версия {latest_version}, загружаем обновление...")
                
                script_response = requests.get(SCRIPT_URL, timeout=10)
                if script_response.status_code == 200:
                    new_code = script_response.text
                    
                    # Перезаписываем текущий файл
                    with open("icepulse.py", "w", encoding="utf-8") as f:
                        f.write(new_code)
                    
                    # Сохраняем новую версию в базу данных клиента!
                    set_setting("current_version", latest_version)
                    
                    print("[+] Обновление успешно установлено! Быстрый перезапуск...\n")
                    time.sleep(1)
                    
                    # Перезапускаем программу в текущем окне
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
        print(f" {C_ICE}{C_BOLD}[3]{C_RESET} Сбросить привязку (Очистка кэша) {C_GRAY}| 🔄 Удалить локальные данные{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[0]{C_RESET} Выход                            {C_GRAY}| ❌ Закрыть программу{C_RESET}")
        print(f"{C_ICE}{C_BOLD}========================================================{C_RESET}")

        choice = (await ainput(f"\n{C_BOLD}Выберите действие (0-3): {C_RESET}")).strip()

        if choice == "0":
            raise SystemExit()

        elif choice == "3":
            if reset_local_data():
                print(f"\n{C_GREEN}✅ Локальные данные и привязки успешно сброшены!{C_RESET}")
            else:
                print(f"\n{C_YELLOW}⚠️ Часть файлов занята процессами, но база пересоздана.{C_RESET}")
            await asyncio.sleep(1.5)
            continue

        elif choice == "1":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== ВХОД В ПРОФИЛЬ ICEPULSE ==={C_RESET}\n")
            email = (await ainput(f"Введите вашу почту (Email) {C_GRAY}[0 - Назад]{C_RESET}: ")).strip().lower()
            if email == "0": continue
            
            password = (await ainput(f"Введите ваш пароль {C_GRAY}[0 - Назад]{C_RESET}: ")).strip()
            if password == "0": continue

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
            if email == "0": continue
            
            password = (await ainput(f"Придумайте пароль (мин. 4 символа) {C_GRAY}[0 - Назад]{C_RESET}: ")).strip()
            if password == "0": continue

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

async def mailing_loop(client: TelegramClient, stop_event: asyncio.Event, email: str, pass_hash: str):
    next_run_times = {}

    while not stop_event.is_set():
        login_ok, is_active, status_msg = await asyncio.to_thread(check_profile_online, email, pass_hash)
        if (not login_ok or not is_active) and "Нет связи" not in status_msg:
            print(f"\n{C_RED}[!] Подписка профиля неактивна! Рассылка остановлена.{C_RESET}")
            stop_event.set()
            break

        ad_mode = get_setting("ad_mode", "")
        ad_text = get_setting("ad_text", "")
        ad_photo = get_setting("ad_photo", "")
        ad_msg_id = int(get_setting("ad_msg_id", "0") or 0)

        saved_msg_obj = None
        if ad_mode == "saved":
            saved_msg_obj = await client.get_messages("me", ids=ad_msg_id)
            if not saved_msg_obj:
                print(f"{C_RED}[!] Пост в 'Избранном' не найден.{C_RESET}")
                stop_event.set()
                break

        with sqlite3.connect(DB_FILE) as conn:
            targets = conn.cursor().execute("SELECT id, chat_entity, topic_id, category, delay_sec FROM targets").fetchall()

        sent_in_this_pass = False
        now_ts = time.time()

        for r_id, chat_entity, topic_id, category, delay_sec in targets:
            if stop_event.is_set():
                break

            if now_ts >= next_run_times.get(r_id, 0):
                now_str = datetime.now().strftime("%H:%M:%S")
                entity = int(chat_entity) if chat_entity.lstrip("-").isdigit() else chat_entity
                topic_label = f" (Ветка: {topic_id})" if topic_id else ""

                try:
                    if ad_mode == "saved" and saved_msg_obj:
                        await client.send_message(entity=entity, message=saved_msg_obj, reply_to=topic_id)
                    else:
                        file_to_send = ad_photo if (ad_photo and os.path.isfile(ad_photo)) else None
                        await client.send_message(entity=entity, message=ad_text, file=file_to_send, reply_to=topic_id)

                    print(f"{C_GRAY}[{now_str}]{C_RESET} {C_ICE}[Кат: {category}]{C_RESET} {C_GREEN}Отправлено:{C_RESET} {chat_entity}{topic_label}")
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
    mode = get_setting("ad_mode", "")
    if mode == "console":
        txt = get_setting("ad_text", "")
        photo = get_setting("ad_photo", "")
        short_txt = (txt[:35] + "...") if len(txt) > 35 else txt
        photo_str = " + Фото" if photo else ""
        return f"{C_GREEN}Текст из консоли: \"{short_txt}\"{photo_str}{C_RESET}"
    elif mode == "saved":
        msg_id = get_setting("ad_msg_id", "0")
        return f"{C_GREEN}Пост из Избранного (ID: {msg_id}){C_RESET}"
    return f"{C_RED}Не задан{C_RESET}"

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
        print(f" {C_ICE}{C_BOLD}[1]{C_RESET} Запустить авторассылку IcePulse       {C_GRAY}| 🚀 Старт отправки сообщений{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[2]{C_RESET} Задать рекламный текст / фото         {C_GRAY}| 📝 Что будем рассылать?{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[3]{C_RESET} Добавить чаты и настроить категории   {C_GRAY}| 📂 Импорт баз из папки или вручную{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[4]{C_RESET} Список чатов базы / Удалить чаты      {C_GRAY}| 📋 Управление добавленными чатами{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[5]{C_RESET} Массово изменить интервал рассылки    {C_GRAY}| ⏱️ Настройка общего таймера{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[6]{C_RESET} Активировать / продлить ключ IcePulse {C_GRAY}| 🔑 Управление подпиской{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[7]{C_RESET} Сменить аккаунт (Очистка сессии)      {C_GRAY}| 🔄 Выйти из текущего Telegram/профиля{C_RESET}")
        print(f" {C_ICE}{C_BOLD}[0]{C_RESET} Выход из программы                    {C_GRAY}| ❌ Закрыть софт{C_RESET}")
        print(f"{C_ICE}{C_BOLD}======================================================================{C_RESET}")

        choice = (await ainput(f"\n{C_BOLD}Выберите пункт меню (0-7): {C_RESET}")).strip()

        if choice == "6":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== АКТИВАЦИЯ КЛЮЧА ==={C_RESET}")
            key_str = (await ainput(f"Введите ваш ключ {C_GRAY}[0 - Отмена]{C_RESET}: ")).strip()
            if key_str == "0": continue
            
            _, msg = await asyncio.to_thread(activate_key_online, email, pass_hash, key_str)
            print(f"\n{msg}")
            await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
            continue

        if choice == "7":
            set_setting("user_email", "")
            set_setting("user_pass_hash", "")
            if reset_local_data():
                print(f"\n{C_GREEN}✅ Сессия Telegram успешно очищена! Программа перезапустится.{C_RESET}")
            await asyncio.sleep(2)
            subprocess.call([sys.executable] + sys.argv)
            sys.exit(0)

        if choice == "0":
            break

        if not is_active:
            print(f"\n{C_RED}Доступ закрыт! Сначала активируйте ключ в пункте [6].{C_RESET}")
            await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
            continue

        if choice == "1":
            if not get_setting("ad_mode"):
                print(f"\n{C_YELLOW}Сначала задайте рекламный пост в пункте [2]!{C_RESET}")
                await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
                continue
            if chats_count == 0:
                print(f"\n{C_YELLOW}Сначала добавьте хотя бы один чат в пункте [3]!{C_RESET}")
                await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")
                continue

            clear_screen()
            print(f"{C_ICE}ICEPULSE АКТИВЕН. Независимые таймеры запущены.{C_RESET}")
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
            print(f"{C_ICE}{C_BOLD}=== НАСТРОЙКА РЕКЛАМНОГО ОБЪЯВЛЕНИЯ ==={C_RESET}\n")
            print(f" {C_BOLD}[1]{C_RESET} Задать свой текст / фото          {C_GRAY}| Ввод текста прямо в консоли{C_RESET}")
            print(f" {C_BOLD}[2]{C_RESET} Взять пост из Избранного          {C_GRAY}| Скопирует последнее сообщение из 'Избранное' в ТГ{C_RESET}")
            sub = (await ainput(f"\n{C_BOLD}Ваш выбор {C_GRAY}(1 или 2 | 0 - Назад):{C_RESET} ")).strip()
            
            if sub == "0": continue

            if sub == "1":
                text_val = (await ainput(f"\n{C_BOLD}Введите рекламный текст{C_RESET} {C_GRAY}[0 - Отмена]{C_RESET}:{C_BOLD}\n-> {C_RESET}")).strip()
                if text_val == "0": continue
                
                if text_val:
                    photo_val = (await ainput(f"{C_BOLD}Путь к фото{C_RESET} {C_GRAY}(Enter - без фото, 0 - Отмена):{C_RESET} ")).strip().strip('"')
                    if photo_val == "0": continue
                    
                    set_setting("ad_mode", "console")
                    set_setting("ad_text", text_val)
                    set_setting("ad_photo", photo_val if os.path.isfile(photo_val) else "")
                    print(f"\n{C_GREEN}✅ Объявление успешно сохранено!{C_RESET}")
            elif sub == "2":
                msgs = await client.get_messages("me", limit=1)
                if msgs:
                    set_setting("ad_mode", "saved")
                    set_setting("ad_msg_id", str(msgs[0].id))
                    print(f"\n{C_GREEN}✅ Пост из Избранного успешно захвачен!{C_RESET}")
                else:
                    print(f"\n{C_RED}[!] У вас пусто в 'Избранном'. Перешлите туда пост и попробуйте снова.{C_RESET}")
            await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")

        elif choice == "3":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== ДОБАВЛЕНИЕ ЧАТОВ В БАЗУ ==={C_RESET}\n")
            print(f" {C_ICE}[1]{C_RESET} Добавить один чат вручную         {C_GRAY}| Вставить ссылку или @username{C_RESET}")
            print(f" {C_ICE}[2]{C_RESET} Импорт базы чатов из файла .TXT   {C_GRAY}| Авто-выбор файлов из папки '{IMPORT_DIR}'{C_RESET}")
            sub = (await ainput(f"\n{C_BOLD}Ваш выбор {C_GRAY}(1-2 | 0 - Назад):{C_RESET} ")).strip()
            
            if sub == "0": continue
            
            targets_to_add = []
            if sub == "1":
                raw = (await ainput(f"\n{C_BOLD}Вставьте ссылку или @username:{C_RESET} {C_GRAY}[0 - Отмена]{C_RESET}\n-> ")).strip()
                if raw == "0": continue
                c, t = parse_single_target(raw)
                if c: targets_to_add.append((c, t))
            elif sub == "2":
                txt_files = [f for f in os.listdir(IMPORT_DIR) if f.endswith('.txt')]
                if not txt_files:
                    print(f"\n{C_YELLOW}[!] В папке '{IMPORT_DIR}' нет текстовых файлов.{C_RESET}")
                    print(f"{C_GRAY}Закиньте туда .txt файлы с чатами (разделитель - пробел или Enter) и возвращайтесь.{C_RESET}")
                else:
                    print(f"\n{C_ICE}📂 Доступные TXT базы в папке '{IMPORT_DIR}':{C_RESET}")
                    for i, file_name in enumerate(txt_files, 1):
                        print(f" {C_BOLD}[{i}]{C_RESET} {file_name}")
                    
                    f_choice = (await ainput(f"\n{C_BOLD}Введите номер нужного файла {C_GRAY}[0 - Отмена]{C_RESET}: ")).strip()
                    if f_choice == "0": continue
                    
                    if f_choice.isdigit() and 1 <= int(f_choice) <= len(txt_files):
                        selected_file = txt_files[int(f_choice)-1]
                        filepath = os.path.join(IMPORT_DIR, selected_file)
                        
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        items = re.split(r'[\s\n]+', content.strip())
                        for item in items:
                            c, t = parse_single_target(item)
                            if c: targets_to_add.append((c, t))
                        print(f"\n{C_GREEN}✅ База '{selected_file}' прочитана! Найдено корректных чатов: {len(targets_to_add)}{C_RESET}")
                    else:
                        print(f"\n{C_RED}[!] Неверный выбор.{C_RESET}")
            
            if targets_to_add:
                print(f"\n{C_ICE}--- НАСТРОЙКА КАТЕГОРИИ ---{C_RESET}")
                cat = (await ainput(f"{C_BOLD}Введите название категории{C_RESET} {C_GRAY}(Enter - 'Основная', 0 - Отмена):{C_RESET} ")).strip()
                if cat == "0": continue
                if not cat: cat = "Основная"
                
                delay_m = (await ainput(f"{C_BOLD}Интервал рассылки в минутах{C_RESET} {C_GRAY}(Enter - 15 мин, 0 - Отмена):{C_RESET} ")).strip()
                if delay_m == "0": continue
                
                delay_s = int(delay_m) * 60 if delay_m.isdigit() and int(delay_m) > 0 else 900
                
                with sqlite3.connect(DB_FILE) as conn:
                    for c, t in targets_to_add:
                        conn.cursor().execute(
                            "INSERT INTO targets (chat_entity, topic_id, category, delay_sec) VALUES (?, ?, ?, ?)", 
                            (c, t, cat, delay_s)
                        )
                    conn.commit()
                print(f"\n{C_GREEN}✅ Успешно добавлено {len(targets_to_add)} чат(ов) в категорию '{cat}'!{C_RESET}")
            
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
                    print(f"[{C_BOLD}ID: {r_id}{C_RESET}] {c_ent}{t_str} | Кат: {C_ICE}{cat}{C_RESET} | {d_sec//60} мин.")
            
            print(f"\n{C_GRAY}Подсказка: Введите 'all' чтобы очистить всю базу разом.{C_RESET}")
            del_id = (await ainput(f"{C_BOLD}Введите ID для удаления{C_RESET} {C_GRAY}(Enter или 0 - Назад):{C_RESET} ")).strip().lower()
            
            if del_id in ["0", ""]: 
                continue
                
            if del_id == 'all':
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("DELETE FROM targets")
                    conn.commit()
                print(f"\n{C_GREEN}✅ Вся база чатов успешно очищена.{C_RESET}")
            elif del_id.isdigit():
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("DELETE FROM targets WHERE id = ?", (int(del_id),))
                    conn.commit()
                print(f"\n{C_GREEN}✅ Чат успешно удален.{C_RESET}")
            await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")

        elif choice == "5":
            clear_screen()
            print(f"{C_ICE}{C_BOLD}=== МАССОВОЕ ИЗМЕНЕНИЕ ИНТЕРВАЛА ==={C_RESET}\n")
            mins = (await ainput(f"{C_BOLD}Введите новый интервал (в минутах) для ВСЕХ чатов в базе {C_GRAY}[0 - Отмена]{C_RESET}:{C_BOLD}\n-> {C_RESET}")).strip()
            
            if mins == "0": continue
            
            if mins.isdigit() and int(mins) > 0:
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("UPDATE targets SET delay_sec = ?", (int(mins) * 60,))
                    conn.commit()
                print(f"\n{C_GREEN}✅ Интервал всех чатов в базе успешно обновлен на {mins} мин.!{C_RESET}")
            else:
                print(f"\n{C_RED}[!] Отмена. Нужно ввести целое число.{C_RESET}")
            await ainput(f"\n{C_GRAY}Нажмите Enter...{C_RESET}")

async def main():
    email, pass_hash = await ensure_authenticated()

    api_id = get_setting("api_id")
    api_hash = get_setting("api_hash")

    if not api_id or not api_hash:
        clear_screen()
        print(f"{C_ICE}{C_BOLD}=== ПЕРВИЧНАЯ НАСТРОЙКА TELEGRAM API ==={C_RESET}")
        print(f"{C_GRAY}Ключи получаются один раз на официальном сайте: https://my.telegram.org{C_RESET}\n")
        api_id = input("Введите ваш API_ID: ").strip()
        api_hash = input("Введите ваш API_HASH: ").strip()
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
            
            print(f"\n{C_GREEN}✅ Успешная авторизация в Telegram через QR-код!{C_RESET}")
            
        except SessionPasswordNeededError:
            print(f"\n{C_YELLOW}[!] На аккаунте включена двухэтапная аутентификация (Облачный пароль).{C_RESET}")
            password = await ainput(f"Введите пароль от аккаунта Telegram {C_GRAY}[0 - Отмена]{C_RESET}: ")
            if password.strip() == "0": sys.exit(0)
            await client.sign_in(password=password.strip())
            print(f"\n{C_GREEN}✅ Успешный вход по облачному паролю!{C_RESET}")
            
        except Exception as e:
            print(f"\n{C_RED}❌ Возникла ошибка при входе по QR-коду: {e}{C_RESET}")
            phone = await ainput(f"\n{C_BOLD}Давайте войдем по номеру.{C_RESET} Введите номер телефона (+380...) {C_GRAY}[0 - Отмена]{C_RESET}: ")
            if phone.strip() == "0": sys.exit(0)
            await client.send_code_request(phone.strip())
            code = await ainput(f"Введите код подтверждения из Telegram {C_GRAY}[0 - Отмена]{C_RESET}: ")
            if code.strip() == "0": sys.exit(0)
            await client.sign_in(phone.strip(), code.strip())
            print(f"\n{C_GREEN}✅ Успешно авторизовано!{C_RESET}")

    await console_menu(client, email, pass_hash)
    await client.disconnect()

if __name__ == "__main__":
    os.system("")
    if os.name == "nt":
        os.system("title IcePulse - Telegram Auto-Poster")
        
    # Инициализация базы данных и проверка обновлений до запуска асинхронного меню
    init_db()
    check_for_updates()
    
    try:
        asyncio.run(main())
    except Exception as e:
        import traceback
        print(f"\nКритическая ошибка:")
        traceback.print_exc()
    finally:
        input("\nНажмите Enter для выхода...")
