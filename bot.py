import sys
import os
import secrets
import requests
import base64
import json

# --- Конфигурация ---
GITHUB_USER = "ironskij501501-hue"
GITHUB_REPO = "LookTV"
CODES_FILE = "codes.txt"
CODES_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{CODES_FILE}"
LAST_UPDATE_FILE = "last_update.txt"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

print(f"DEBUG: GITHUB_TOKEN present, length={len(GITHUB_TOKEN) if GITHUB_TOKEN else 0}", file=sys.stderr)
print(f"DEBUG: TELEGRAM_TOKEN present, length={len(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else 0}", file=sys.stderr)

if not GITHUB_TOKEN or not TELEGRAM_TOKEN:
    print("ERROR: Missing token(s)", file=sys.stderr)
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
        print("DEBUG: codes.txt not found, will create", file=sys.stderr)
        return "", None
    else:
        print(f"ERROR: get_codes_file status {resp.status_code} {resp.text}", file=sys.stderr)
        return None, None

def update_codes_file(content, sha=None):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    data = {
        "message": "Update codes.txt",
        "content": encoded,
        "branch": "main"
    }
    if sha:
        data["sha"] = sha

    print(f"DEBUG: PUT {CODES_URL}", file=sys.stderr)
    print(f"DEBUG: data = {json.dumps(data, indent=2)}", file=sys.stderr)

    resp = requests.put(CODES_URL, headers=headers, json=data)
    success = resp.status_code in [200, 201]
    if not success:
        print(f"ERROR: update_codes_file failed: {resp.status_code} {resp.text}", file=sys.stderr)
    else:
        print("DEBUG: update_codes_file succeeded", file=sys.stderr)
    return success

def generate_code():
    return f"LOOKTV_{secrets.token_hex(4).upper()}"

def add_code_to_file(code):
    print(f"DEBUG: add_code_to_file({code})", file=sys.stderr)
    content, sha = get_codes_file()
    if content is None:
        return False
    if content and f"{code}:" in content:
        print(f"DEBUG: code {code} already exists", file=sys.stderr)
        return False
    new_line = f"{code}:unused"
    new_content = f"{content}\n{new_line}" if content else new_line
    print(f"DEBUG: new_content length {len(new_content)}", file=sys.stderr)
    return update_codes_file(new_content, sha)

# --- Telegram функции ---
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=5)
        print(f"DEBUG: send_message response status {resp.status_code}", file=sys.stderr)
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
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
    try:
        resp = requests.get(url, timeout=5)
        print(f"DEBUG: deleteWebhook response {resp.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR deleteWebhook: {e}", file=sys.stderr)

# --- Основная логика обработки обновлений ---
def process_updates():
    print("Processing updates...", file=sys.stderr)
    delete_webhook()

    last_id = None
    if os.path.exists(LAST_UPDATE_FILE):
        try:
            with open(LAST_UPDATE_FILE, "r") as f:
                last_id = int(f.read().strip())
            print(f"DEBUG: last_id from file = {last_id}", file=sys.stderr)
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
                print(f"DEBUG: generated code {code}", file=sys.stderr)
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
            print(f"DEBUG: saved last_update_id = {new_last_id}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR saving last_update.txt: {e}", file=sys.stderr)

# --- Точка входа ---
if __name__ == "__main__":
    process_updates()
    print("Done", file=sys.stderr)
