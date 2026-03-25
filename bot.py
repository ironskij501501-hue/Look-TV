import sys
import os
import secrets
import requests
import base64

# --- Конфигурация ---
GITHUB_USER = "ironskij501501-hue"
GITHUB_REPO = "LookTV"
CODES_FILE = "codes.txt"
CODES_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{CODES_FILE}"
LAST_UPDATE_FILE = "last_update.txt"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not GITHUB_TOKEN:
    print("ERROR: GITHUB_TOKEN not set", file=sys.stderr)
    sys.exit(1)
if not TELEGRAM_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
    sys.exit(1)

# --- GitHub API функции ---
def get_codes_file():
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
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    data = {"message": "Update codes.txt", "content": encoded}
    if sha:
        data["sha"] = sha
    resp = requests.put(CODES_URL, headers=headers, json=data)
    return resp.status_code in [200, 201]

def generate_code():
    return f"LOOKTV_{secrets.token_hex(4).upper()}"

def add_code_to_file(code):
    content, sha = get_codes_file()
    if content is None:
        return False
    if content and f"{code}:" in content:
        return False
    new_line = f"{code}:unused"
    new_content = f"{content}\n{new_line}" if content else new_line
    return update_codes_file(new_content, sha)

# --- Telegram функции ---
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

def delete_webhook():
    """Удаляем вебхук, если он активен"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            print("Webhook deleted successfully", file=sys.stderr)
        else:
            print(f"Failed to delete webhook: {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"Error deleting webhook: {e}", file=sys.stderr)

def commit_file(file_path, content, commit_message):
    """Создаёт или обновляет файл в репозитории"""
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    # Проверяем существование файла
    get_resp = requests.get(url, headers=headers)
    sha = None
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")
        print(f"File {file_path} exists, sha={sha}", file=sys.stderr)
    elif get_resp.status_code == 404:
        print(f"File {file_path} does not exist, will create", file=sys.stderr)
    else:
        print(f"Unexpected status checking {file_path}: {get_resp.status_code}", file=sys.stderr)
        return False

    # Подготовка данных
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    data = {
        "message": commit_message,
        "content": encoded,
        "branch": "main"   # явно указываем ветку
    }
    if sha:
        data["sha"] = sha

    put_resp = requests.put(url, headers=headers, json=data)
    if put_resp.status_code in [200, 201]:
        print(f"Successfully committed {file_path}", file=sys.stderr)
        return True
    else:
        print(f"Error committing {file_path}: {put_resp.status_code} {put_resp.text}", file=sys.stderr)
        return False

# --- Основная логика обработки обновлений ---
def process_updates():
    print("Processing updates...", file=sys.stderr)

    # Удаляем вебхук, если он активен (чтобы polling работал)
    delete_webhook()

    last_id = None
    if os.path.exists(LAST_UPDATE_FILE):
        try:
            with open(LAST_UPDATE_FILE, "r") as f:
                last_id = int(f.read().strip())
            print(f"Last update ID from file: {last_id}", file=sys.stderr)
        except:
            pass

    updates = get_updates(offset=last_id)
    if not updates:
        print("No new updates", file=sys.stderr)
        return

    print(f"Got {len(updates)} updates", file=sys.stderr)
    new_last_id = last_id
    for update in updates:
        update_id = update["update_id"]
        message = update.get("message")
        if message:
            user_id = message["from"]["id"]
            text = message.get("text", "")
            print(f"User {user_id}, text: {text}", file=sys.stderr)
            if text == "/buy":
                code = generate_code()
                if add_code_to_file(code):
                    send_message(user_id, f"✅ Ваш код активации: `{code}`")
                else:
                    send_message(user_id, "❌ Ошибка генерации кода. Обратитесь к администратору.")
            else:
                send_message(user_id, "Используйте /buy для получения кода активации.")
        if new_last_id is None or update_id >= new_last_id:
            new_last_id = update_id + 1

    if new_last_id is not None:
        try:
            with open(LAST_UPDATE_FILE, "w") as f:
                f.write(str(new_last_id))
            print(f"Saved last_update_id = {new_last_id}", file=sys.stderr)
            if commit_file(LAST_UPDATE_FILE, str(new_last_id), "Update last_update_id"):
                print("Committed last_update.txt", file=sys.stderr)
            else:
                print("Failed to commit last_update.txt", file=sys.stderr)
        except Exception as e:
            print(f"Error saving last_update.txt: {e}", file=sys.stderr)

# --- Точка входа ---
if __name__ == "__main__":
    process_updates()
    print("Done", file=sys.stderr)

# --- Точка входа ---
if __name__ == "__main__":
    process_updates()
    print("Done", file=sys.stderr)
