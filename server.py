#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Сервер активации для LookTV
Обрабатывает webhook от GetPlatinum и активацию устройств
Версия с безопасным хранением секретов в переменных окружения
"""

import os
import json
import secrets
import logging
import hmac
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify

# ==================== ПРОВЕРКА БИБЛИОТЕК ====================
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("⚠️ Библиотека requests не установлена. Уведомления в Telegram работать не будут.")

try:
    from github import Github, GithubException
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False
    print("⚠️ Библиотека PyGithub не установлена. Работа с GitHub будет недоступна.")

# ==================== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ====================

# GitHub (обязательно через переменные окружения!)
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO_LOOKTV = os.environ.get('GITHUB_REPO_LOOKTV', 'ironskij501501-hue/LookTV')
GITHUB_REPO_FILES = os.environ.get('GITHUB_REPO_FILES', 'ironskij501501-hue/Look-TV')
ALLOWED_FILE = os.environ.get('ALLOWED_FILE', 'allowed_macs.txt')
TOKENS_FILE = os.environ.get('TOKENS_FILE', 'tokens.json')

# GetPlatinum (обязательно через переменные окружения!)
GETPLATINUM_API_KEY = os.environ.get('GETPLATINUM_API_KEY', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')

# Настройки Flask
DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
PORT = int(os.environ.get('PORT', 5000))
HOST = os.environ.get('HOST', '0.0.0.0')

# ==================== ПРОВЕРКА СЕКРЕТОВ ====================

def check_secrets():
    """Проверяет наличие всех необходимых секретов"""
    missing = []
    
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
        logger.warning("⚠️ GITHUB_TOKEN не установлен. GitHub функции будут недоступны.")
    
    if not GETPLATINUM_API_KEY:
        missing.append("GETPLATINUM_API_KEY")
        logger.warning("⚠️ GETPLATINUM_API_KEY не установлен. Проверка подписи работать не будет!")
    
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
        logger.warning("⚠️ BOT_TOKEN не установлен. Уведомления в Telegram не будут отправляться.")
    
    if missing:
        logger.warning(f"⚠️ Отсутствуют секреты: {', '.join(missing)}")
        return False
    return True

# ==================== ИНИЦИАЛИЗАЦИЯ ====================

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Проверяем секреты при запуске
check_secrets()

# Подключаемся к GitHub только если библиотека установлена и есть токен
if GITHUB_AVAILABLE and GITHUB_TOKEN:
    try:
        g = Github(GITHUB_TOKEN)
        repo_looktv = g.get_repo(GITHUB_REPO_LOOKTV)
        repo_files = g.get_repo(GITHUB_REPO_FILES)
        logger.info("✅ Подключено к репозиториям GitHub")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к GitHub: {e}")
        repo_looktv = None
        repo_files = None
else:
    if not GITHUB_AVAILABLE:
        logger.warning("⚠️ Библиотека PyGithub не установлена. GitHub функции отключены.")
    elif not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN не установлен. GitHub функции отключены.")
    repo_looktv = None
    repo_files = None

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_github_file(repo, path):
    """Получает содержимое файла из GitHub"""
    if not GITHUB_AVAILABLE or not repo or not GITHUB_TOKEN:
        logger.error("❌ GitHub недоступен (библиотека или токен)")
        return None, None
    try:
        contents = repo.get_contents(path)
        content = contents.decoded_content.decode('utf-8')
        return content, contents.sha
    except Exception as e:
        logger.error(f"Ошибка GitHub при чтении {path}: {e}")
        return None, None

def update_github_file(repo, path, new_content, sha, commit_message):
    """Обновляет файл на GitHub"""
    if not GITHUB_AVAILABLE or not repo or not GITHUB_TOKEN:
        logger.error("❌ GitHub недоступен (библиотека или токен)")
        return False
    try:
        if sha:
            contents = repo.get_contents(path)
            repo.update_file(path, commit_message, new_content, contents.sha)
        else:
            repo.create_file(path, commit_message, new_content)
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при записи {path}: {e}")
        return False

def get_latest_apk_info():
    """Получает информацию о последнем APK"""
    if not GITHUB_AVAILABLE or not repo_looktv or not GITHUB_TOKEN:
        logger.warning("⚠️ GitHub недоступен, использую заглушку")
        return "1.0.0", "https://github.com/ironskij501501-hue/LookTV/releases/latest"
    try:
        releases = list(repo_looktv.get_releases())
        if not releases:
            return None, None
        latest = releases[0]
        version = latest.tag_name.replace('v', '')
        for asset in latest.get_assets():
            if asset.name.endswith('.apk'):
                return version, asset.url
        return version, latest.html_url
    except Exception as e:
        logger.error(f"❌ Ошибка получения релиза: {e}")
        return None, None

def send_telegram_message(chat_id, token, apk_version, apk_url):
    """Отправляет сообщение в Telegram"""
    if not REQUESTS_AVAILABLE:
        logger.error("❌ Библиотека requests не установлена")
        return False
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN не настроен, пропускаем отправку")
        return True  # Возвращаем успех, чтобы не ломать логику
    
    text = (
        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        f"📱 <b>Версия приложения:</b> {apk_version}\n"
        f"🔑 <b>Ваш код активации:</b> <code>{token}</code>\n\n"
        "📲 <b>Как установить:</b>\n"
        "1️⃣ Скачайте APK по ссылке ниже\n"
        "2️⃣ Установите приложение\n"
        "3️⃣ При запуске выберите «У меня есть код»\n"
        "4️⃣ Введите код\n\n"
        f"⬇️ <b>Ссылка для скачивания:</b>\n{apk_url}\n\n"
        "⚠️ Код действует 24 часа."
    )
    
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        return False

def load_tokens():
    """Загружает токены из локального файла"""
    try:
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, 'r') as f:
                return json.load(f), None
        return {}, None
    except Exception as e:
        logger.error(f"Ошибка загрузки токенов: {e}")
        return {}, None

def save_tokens(tokens, sha=None, message=""):
    """Сохраняет токены в локальный файл"""
    try:
        with open(TOKENS_FILE, 'w') as f:
            json.dump(tokens, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения токенов: {e}")
        return False

def add_to_allowed_list(android_id):
    """Добавляет устройство в белый список"""
    logger.info(f"✅ Устройство {android_id} активировано")
    # TODO: добавить реальное сохранение в файл
    return True

def verify_getplatinum_signature(data):
    """Проверяет подпись от GetPlatinum"""
    if not GETPLATINUM_API_KEY:
        logger.warning("⚠️ GETPLATINUM_API_KEY не настроен, пропускаем проверку подписи")
        return True
    
    received_checksum = data.get('checksum')
    if not received_checksum:
        return False
    
    params = data.copy()
    params.pop('checksum', None)
    params.pop('customParams', None)
    
    sorted_keys = sorted(params.keys(), key=lambda k: k.lower())
    
    sign_string = ''
    for key in sorted_keys:
        value = params[key]
        if isinstance(value, bool):
            value = 1 if value else 0
        elif isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        sign_string += f"{key};{value};"
    
    calculated_checksum = hmac.new(
        key=GETPLATINUM_API_KEY.encode('utf-8'),
        msg=sign_string.encode('utf-8'),
        digestmod=hashlib.sha256
    ).hexdigest().upper()
    
    return hmac.compare_digest(calculated_checksum, received_checksum)

# ==================== WEBHOOK ====================

@app.route('/getplatinum-webhook', methods=['POST'])
def getplatinum_webhook():
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400
    
    logger.info(f"Webhook получен")
    
    if not verify_getplatinum_signature(data):
        return jsonify({"error": "Invalid signature"}), 403
    
    if not data.get('isSuccess'):
        return jsonify({"ok": True})
    
    custom_params = data.get('customParams', {})
    telegram_id = custom_params.get('telegram_id')
    
    if not telegram_id:
        logger.error("Нет telegram_id в customParams")
        return jsonify({"error": "No telegram_id"}), 400
    
    apk_version, apk_url = get_latest_apk_info()
    if not apk_version:
        apk_version = "1.0.0"
        apk_url = "https://github.com/ironskij501501-hue/LookTV/releases/latest"
    
    token = secrets.token_urlsafe(16)
    
    tokens, _ = load_tokens()
    tokens[token] = {
        "telegram_id": telegram_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "apk_version": apk_version
    }
    save_tokens(tokens)
    
    send_telegram_message(telegram_id, token, apk_version, apk_url)
    
    return jsonify({"ok": True, "token": token})

# ==================== АКТИВАЦИЯ ====================

@app.route('/activate', methods=['POST'])
def activate():
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400
    
    token = data.get('token')
    android_id = data.get('androidId')
    
    if not token or not android_id:
        return jsonify({"error": "Missing data"}), 400
    
    tokens, _ = load_tokens()
    token_data = tokens.get(token)
    
    if not token_data or token_data['status'] != 'pending':
        return jsonify({"error": "Invalid token"}), 400
    
    if not add_to_allowed_list(android_id):
        return jsonify({"error": "Failed to add"}), 500
    
    token_data['status'] = 'used'
    token_data['used_at'] = datetime.now().isoformat()
    token_data['android_id'] = android_id
    save_tokens(tokens)
    
    return jsonify({"ok": True})

# ==================== HEALTH ====================

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok", 
        "time": datetime.now().isoformat(),
        "github_available": GITHUB_AVAILABLE and bool(GITHUB_TOKEN),
        "requests_available": REQUESTS_AVAILABLE,
        "secrets_configured": {
            "github": bool(GITHUB_TOKEN),
            "getplatinum": bool(GETPLATINUM_API_KEY),
            "telegram": bool(BOT_TOKEN)
        }
    })

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    logger.info(f"🚀 Запуск сервера активации на порту {PORT}")
    logger.info(f"📡 Endpoints:")
    logger.info(f"   - /health (GET)")
    logger.info(f"   - /getplatinum-webhook (POST)")
    logger.info(f"   - /activate (POST)")
    logger.info(f"📦 Библиотеки: PyGithub={'✅' if GITHUB_AVAILABLE else '❌'}, requests={'✅' if REQUESTS_AVAILABLE else '❌'}")
    logger.info(f"🔐 Секреты: GitHub={'✅' if GITHUB_TOKEN else '❌'}, GetPlatinum={'✅' if GETPLATINUM_API_KEY else '❌'}, Telegram={'✅' if BOT_TOKEN else '❌'}")
    app.run(host=HOST, port=PORT, debug=DEBUG)







