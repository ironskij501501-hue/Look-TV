import sys
import secrets
import requests
import base64
import os

GITHUB_TOKEN = os.environ['GITHUB_TOKEN']        # автоматически доступен в Actions
TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
GITHUB_USER = "ironskij501501-hue"
GITHUB_REPO = "LookTV"
CODES_FILE = "codes.txt"
CODES_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{CODES_FILE}"

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=data)

def get_codes_file():
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(CODES_URL, headers=headers)
    if resp.status_code == 200:
        content = resp.json()['content']
        return base64.b64decode(content).decode('utf-8'), resp.json()['sha']
    return "", None

def update_codes_file(content, sha=None):
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "message": "Add code",
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha
    }
    resp = requests.put(CODES_URL, headers=headers, json=data)
    return resp.status_code in [200, 201]

def generate_code():
    return f"LOOKTV_{secrets.token_hex(4).upper()}"

def add_code_to_file(code):
    current, sha = get_codes_file()
    if current and f"{code}:" in current:
        return False
    new_line = f"{code}:unused"
    new_content = f"{current}\n{new_line}" if current else new_line
    return update_codes_file(new_content, sha)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    user_id = sys.argv[1]
    text = sys.argv[2].strip()

    if text == "/buy":
        code = generate_code()
        if add_code_to_file(code):
            send_message(user_id, f"✅ Ваш код: `{code}`")
        else:
            send_message(user_id, "❌ Ошибка генерации кода.")
    else:
        send_message(user_id, "Используйте /buy для получения кода.")
