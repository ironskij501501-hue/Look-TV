import sys
import os
import time
import secrets
import requests
import base64

# Принудительный вывод в stderr для отладки
print("DEBUG: bot.py started", file=sys.stderr)
sys.stderr.flush()

# --- Конфигурация ---
GITHUB_USER = "ironskij501501-hue"
GITHUB_REPO = "LookTV"
CODES_FILE = "codes.txt"
CODES_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{CODES_FILE}"

# Токены из переменных окружения (должны быть заданы в GitHub Secrets)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not GITHUB_TOKEN:
    print("ERROR: GITHUB_TOKEN not set", file=sys.stderr)
    sys.exit(1)
if not TELEGRAM_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
    sys.exit(1)

print(f"DEBUG: GITHUB_TOKEN length={len(GITHUB_TOKEN)}", file=sys.stderr)
print(f"DEBUG: TELEGRAM_TOKEN length={len(TELEGRAM_TOKEN)}", file=sys.stderr)

# --- Функции для работы с GitHub API ---
def get_codes_file():
    """Получает текущее содержимое и SHA файла codes.txt"""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(CODES_URL, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]
    elif resp.status_code == 404:
        return "", None
    else:
        print(f"ERROR: get_codes_file status {resp.status_code}", file=sys.stderr)
        return None, None

def update_codes_file(content, sha=None):
    """Обновляет файл codes.txt на GitHub"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    data = {
        "message": "Update codes.txt",
        "content": encoded
    }
    if sha:
        data["sha"] = sha
    resp = requests.put(CODES_URL, headers=headers, json=data)
    return resp.status_code in [200, 201]

def generate_code():
    """Генерирует код вида LOOKTV_XXXXXXXX"""
    return f"LOOKTV_{secrets.token_hex(4).upper()}"

def add_code_to_file(code):
    """Добавляет код в файл со статусом unused"""
    content, sha = get_codes_file()
    if content is None:
        return False
    # Проверка, что код уже существует
    if content and f"{code}:" in content:
        return False
    new_line = f"{code}:unused"
    new_content = f"{content}\n{new_line}" if content else new_line
    return update_codes_file(new_content, sha)

# --- Функции Telegram ---
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"ERROR sending message: {e}", file=sys.stderr)

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 10, "offset": offset}
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("ok"):
            return data.get("result", [])
        else:
            print(f"ERROR getUpdates: {data}", file=sys.stderr)
            return []
    except Exception as e:
        print(f"ERROR getUpdates: {e}", file=sys.stderr)
        return []

# --- Обработка обновлений (polling) ---
def process_updates():
    print("DEBUG: process_updates() started", file=sys.stderr)
    last_update_file = "last_update.txt"
    last_id = None
    # Пытаемся прочитать сохранённый ID
    try:
        if os.path.exists(last_update_file):
            with open(last_update_file, "r") as f:
                last_id = int(f.read().strip())
    except Exception as e:
        print(f"DEBUG: could not read last_update.txt: {e}", file=sys.stderr)

    updates = get_updates(offset=last_id)
    print(f"DEBUG: got {len(updates)} updates", file=sys.stderr)
    for update in updates:
        update_id = update.get("update_id")
        if update_id is None:
            continue
        message = update.get("message")
        if message:
            user_id = message.get("from", {}).get("id")
            text = message.get("text", "")
            print(f"DEBUG: user {user_id}, text: {text}", file=sys.stderr)
            if text == "/buy":
                code = generate_code()
                if add_code_to_file(code):
                    send_message(user_id, f"✅ Ваш код активации: `{code}`")
                    print(f"DEBUG: generated code {code} for {user_id}", file=sys.stderr)
                else:
                    send_message(user_id, "❌ Ошибка генерации кода. Обратитесь к администратору.")
            else:
                send_message(user_id, "Используйте /buy для получения кода активации.")
        # Сохраняем последний обработанный ID
        if last_id is None or update_id >= last_id:
            last_id = update_id + 1

    # Сохраняем новый offset
    if last_id is not None:
        try:
            with open(last_update_file, "w") as f:
                f.write(str(last_id))
            print(f"DEBUG: saved last_update_id = {last_id}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR saving last_update.txt: {e}", file=sys.stderr)

# --- Точка входа ---
if __name__ == "__main__":
    print("DEBUG: entering __main__", file=sys.stderr)
    # Если передан хотя бы один аргумент, считаем, что это ручной запуск с user_id и text
    if len(sys.argv) >= 3:
        print("DEBUG: manual mode", file=sys.stderr)
        user_id = sys.argv[1]
        text = sys.argv[2]
        if text == "/buy":
            code = generate_code()
            if add_code_to_file(code):
                send_message(user_id, f"✅ Ваш код активации: `{code}`")
            else:
                send_message(user_id, "❌ Ошибка генерации кода.")
        else:
            send_message(user_id, "Используйте /buy для получения кода.")
    else:
        # Режим polling — бесконечный цикл
        print("DEBUG: polling mode (no arguments)", file=sys.stderr)
        while True:
            try:
                process_updates()
            except Exception as e:
                print(f"ERROR in polling loop: {e}", file=sys.stderr)
            time.sleep(300)  # 5 минут
