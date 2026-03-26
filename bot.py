import sys
import os
import secrets
import requests
import base64
import json
import time
import urllib.parse

# --- Конфигурация ---
GITHUB_USER = "ironskij501501-hue"
GITHUB_REPO = "LookTV"
CODES_FILE = "codes.txt"
CODES_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{CODES_FILE}"
LAST_UPDATE_FILE = "last_update.txt"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# --- Конфигурация GetPlatinum ---
GETPLATINUM_API_KEY = os.environ.get("GETPLATINUM_API_KEY")
GETPLATINUM_ACCOUNT = "iptvclub"

# Выберите вариант: 1 – с /public и Bearer, 2 – без /public и Bearer, 3 – X-API-Key без /public
AUTH_VARIANT = 2  # меняйте 1, 2, 3

if AUTH_VARIANT == 1:
    GETPLATINUM_BASE_URL = f"https://{GETPLATINUM_ACCOUNT}.getplatinum.ru/api/public"
    AUTH_HEADER = {"Authorization": f"Bearer {GETPLATINUM_API_KEY}"}
elif AUTH_VARIANT == 2:
    GETPLATINUM_BASE_URL = f"https://{GETPLATINUM_ACCOUNT}.getplatinum.ru/api"
    AUTH_HEADER = {"Authorization": f"Bearer {GETPLATINUM_API_KEY}"}
elif AUTH_VARIANT == 3:
    GETPLATINUM_BASE_URL = f"https://{GETPLATINUM_ACCOUNT}.getplatinum.ru/api"
    AUTH_HEADER = {"X-API-Key": GETPLATINUM_API_KEY}
else:
    GETPLATINUM_BASE_URL = f"https://{GETPLATINUM_ACCOUNT}.getplatinum.ru/api"
    AUTH_HEADER = {"Authorization": f"Bearer {GETPLATINUM_API_KEY}"}

print(f"DEBUG: GITHUB_TOKEN present, length={len(GITHUB_TOKEN) if GITHUB_TOKEN else 0}", file=sys.stderr)
print(f"DEBUG: TELEGRAM_TOKEN present, length={len(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else 0}", file=sys.stderr)
print(f"DEBUG: GETPLATINUM_API_KEY present, length={len(GETPLATINUM_API_KEY) if GETPLATINUM_API_KEY else 0}", file=sys.stderr)
print(f"DEBUG: GETPLATINUM_BASE_URL = {GETPLATINUM_BASE_URL}", file=sys.stderr)
print(f"DEBUG: AUTH_HEADER keys = {list(AUTH_HEADER.keys())}", file=sys.stderr)

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
        "branch": "main"   # если ветка master – замените
    }
    if sha:
        data["sha"] = sha
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
def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
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

# --- Функции для работы с GetPlatinum (с использованием AUTH_HEADER) ---
def init_payment_url(user_id):
    headers = AUTH_HEADER.copy()
    headers["Content-Type"] = "application/json"

    deal_id = f"LOOKTV_{user_id}_{int(time.time())}_{secrets.token_hex(4)}"
    amount = 10000  # 100 рублей – измените на свою цену в копейках
    client_email = f"user{user_id}@looktv.temp"

    # Шаг 1: инициализация заказа
    deal_payload = {
        "dealId": deal_id,
        "currency": "RUB",
        "amount": amount,
        "positions": [
            {
                "name": "Активация LookTV",
                "price": amount,
                "quantity": 1,
                "vat": "none"
            }
        ],
        "clientParams": {
            "clientId": str(user_id),
            "email": client_email
        }
    }
    url_deal = f"{GETPLATINUM_BASE_URL}/init-deal"
    try:
        resp = requests.post(url_deal, headers=headers, json=deal_payload, timeout=10)
        print(f"DEBUG: getplatinum init-deal response {resp.status_code}", file=sys.stderr)
        print(f"DEBUG: getplatinum init-deal body {resp.text}", file=sys.stderr)
        if resp.status_code != 200:
            print(f"ERROR: init-deal failed with status {resp.status_code}", file=sys.stderr)
            return None, None
        deal_data = resp.json()
        if deal_data.get("errorCode") != 0:
            print(f"ERROR: init-deal returned error {deal_data}", file=sys.stderr)
            return None, None
        payment_systems = deal_data.get("paymentSystems", [])
        if not payment_systems:
            print("ERROR: no payment systems available", file=sys.stderr)
            return None, None
        ps = payment_systems[0]
        payment_system_code = ps["code"]
        methods = ps.get("methods", [])
        payment_method_code = methods[0]["code"] if methods else None
        print(f"DEBUG: using paymentSystem={payment_system_code}, method={payment_method_code}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: init-deal exception {e}", file=sys.stderr)
        return None, None

    # Шаг 2: инициализация платежа
    payment_payload = {
        "dealId": deal_id,
        "currency": "RUB",
        "amount": amount,
        "paymentSystem": payment_system_code,
        "paymentMethod": payment_method_code,
        "notificationUrl": "https://google.com",
        "successUrl": f"https://t.me/LookTVhelper_bot?start=pay_{deal_id}",
        "failUrl": f"https://t.me/LookTVhelper_bot?start=pay_failed_{deal_id}",
        "customParams": {
            "user_id": user_id,
            "deal_id": deal_id
        }
    }
    url_payment = f"{GETPLATINUM_BASE_URL}/init-payment"
    try:
        resp = requests.post(url_payment, headers=headers, json=payment_payload, timeout=10)
        print(f"DEBUG: getplatinum init-payment response {resp.status_code}", file=sys.stderr)
        print(f"DEBUG: getplatinum init-payment body {resp.text}", file=sys.stderr)
        if resp.status_code != 200:
            print(f"ERROR: init-payment failed with status {resp.status_code}", file=sys.stderr)
            return None, None
        payment_data = resp.json()
        form_url = payment_data.get("formUrl")
        if form_url:
            return form_url, deal_id
        else:
            print(f"ERROR: no formUrl in response {payment_data}", file=sys.stderr)
            return None, None
    except Exception as e:
        print(f"ERROR: init-payment exception {e}", file=sys.stderr)
        return None, None

def check_payment_status(deal_id):
    headers = AUTH_HEADER.copy()
    headers["Content-Type"] = "application/json"
    payload = {"dealId": deal_id}
    url = f"{GETPLATINUM_BASE_URL}/status"
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"DEBUG: getplatinum status response {resp.status_code}", file=sys.stderr)
        print(f"DEBUG: getplatinum status body {resp.text}", file=sys.stderr)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("isSuccess") is True
        else:
            return False
    except Exception as e:
        print(f"ERROR: getplatinum status exception {e}", file=sys.stderr)
        return False

# --- Обработка обновлений ---
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
        if not message:
            continue

        user_id = message["from"]["id"]
        text = message.get("text", "")

        print(f"User {user_id}, text: {text}", file=sys.stderr)

        if text.startswith("/start"):
            parts = text.split()
            param = parts[1] if len(parts) > 1 else None

            if param and param.startswith("pay_"):
                deal_id = param[4:]
                if check_payment_status(deal_id):
                    code = generate_code()
                    if add_code_to_file(code):
                        send_message(user_id, f"✅ Оплата подтверждена!\nВаш код активации: `{code}`")
                    else:
                        send_message(user_id, "❌ Ошибка генерации кода. Обратитесь к администратору.")
                else:
                    send_message(user_id, "❌ Оплата не найдена или не подтверждена. Если вы оплатили, подождите несколько минут и снова нажмите /start. Или напишите /buy для получения кода.")
                continue
            elif param and param.startswith("pay_failed_"):
                send_message(user_id, "❌ Оплата не удалась. Попробуйте ещё раз через /start или обратитесь в поддержку.")
                continue

            pay_link, deal_id = init_payment_url(user_id)
            if pay_link:
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "💳 Оплатить", "url": pay_link}]
                    ]
                }
                send_message(
                    user_id,
                    "Добро пожаловать в LookTV!\n\n"
                    "Для получения кода активации нажмите кнопку «Оплатить». "
                    "После успешной оплаты вы автоматически получите код.",
                    reply_markup=keyboard
                )
            else:
                send_message(user_id, "❌ Ошибка создания платёжной ссылки. Пожалуйста, попробуйте позже или обратитесь к администратору.")
            continue

        if text == "/buy":
            code = generate_code()
            if add_code_to_file(code):
                send_message(user_id, f"✅ Ваш код активации: `{code}`")
            else:
                send_message(user_id, "❌ Ошибка генерации кода. Обратитесь к администратору.")
            continue

        send_message(user_id, "Используйте /start для начала или /buy для получения кода.")

        if new_last_id is None or update_id >= new_last_id:
            new_last_id = update_id + 1

    if new_last_id is not None:
        try:
            with open(LAST_UPDATE_FILE, "w") as f:
                f.write(str(new_last_id))
            print(f"DEBUG: saved last_update_id = {new_last_id}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR saving last_update.txt: {e}", file=sys.stderr)

if __name__ == "__main__":
    process_updates()
    print("Done", file=sys.stderr)
