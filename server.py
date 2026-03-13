#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Сервер активации для LookTV
Обрабатывает webhook от GetPlatinum и активацию устройств
"""

import os
import json
import secrets
import logging
import hmac
import hashlib
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from github import Github, GithubException

# ==================== НАСТРОЙКИ ====================

# GitHub
GITHUB_TOKEN = "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"
GITHUB_REPO_LOOKTV = "ironskij501501-hue/LookTV"
GITHUB_REPO_FILES = "ironskij501501-hue/Look-TV"
ALLOWED_FILE = "allowed_macs.txt"
TOKENS_FILE = "tokens.json"

# GetPlatinum
GETPLATINUM_API_KEY = "PdsbGpgy6gsAUYEex7zfku7M25jq62dv4XUmftSWMweNOZfRRszB6Sh7oLiR6gXS"  # ЗАМЕНИТЕ
BOT_TOKEN = "8533610372:AAEjpiOJEXPR9HInTGER1vIluZCWceSjNcg"  # ЗАМЕНИТЕ

# Настройки Flask
DEBUG = False
PORT = 5000
HOST = "0.0.0.0"

# ==================== ИНИЦИАЛИЗАЦИЯ ====================

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    g = Github(GITHUB_TOKEN)
    repo_looktv = g.get_repo(GITHUB_REPO_LOOKTV)
    repo_files = g.get_repo(GITHUB_REPO_FILES)
    logger.info("✅ Подключено к репозиториям GitHub")
except Exception as e:
    logger.error(f"❌ Ошибка подключения к GitHub: {e}")
    repo_looktv = None
    repo_files = None

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_github_file(repo, path):
    try:
        contents = repo.get_contents(path)
        content = contents.decoded_content.decode('utf-8')
        return content, contents.sha
    except GithubException as e:
        if e.status == 404:
            return None, None
        else:
            logger.error(f"Ошибка GitHub при чтении {path}: {e}")
            return None, None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при чтении {path}: {e}")
        return None, None

def update_github_file(repo, path, new_content, sha, commit_message):
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
    try:
        if not repo_looktv:
            return None, None
        releases = list(repo_looktv.get_releases())
        if not releases:
            return None, None
        latest = releases[0]
        version = latest.tag_name.replace('v', '')
        for asset in latest.get_assets():
            if asset.name.endswith('.apk'):
                return version, asset.url
        return None, None
    except Exception as e:
        logger.error(f"❌ Ошибка получения релиза: {e}")
        return None, None

def send_telegram_message(chat_id, token, apk_version, apk_url):
    if not BOT_TOKEN or BOT_TOKEN == "ваш_токен_бота":
        return False
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
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
        return True
    except:
        return False

def load_tokens():
    content, sha = get_github_file(repo_files, TOKENS_FILE)
    if content is None:
        return {}, None
    try:
        return json.loads(content), sha
    except:
        return {}, None

def save_tokens(tokens, sha, message="Update tokens"):
    new_content = json.dumps(tokens, indent=2, ensure_ascii=False)
    return update_github_file(repo_files, TOKENS_FILE, new_content, sha, message)

def add_to_allowed_list(android_id):
    content, sha = get_github_file(repo_files, ALLOWED_FILE)
    if content is None:
        content = ""
    else:
        content = content.rstrip() + "\n"
    if android_id in content:
        return True
    new_line = f"{android_id} # активирован {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    return update_github_file(repo_files, ALLOWED_FILE, content + new_line, sha, f"Add {android_id}")

def verify_getplatinum_signature(data):
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
    
    logger.info(f"Webhook получен: {json.dumps(data, indent=2)}")
    
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
        return jsonify({"error": "No APK found"}), 500
    
    token = secrets.token_urlsafe(16)
    
    tokens, sha = load_tokens()
    tokens[token] = {
        "telegram_id": telegram_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "apk_version": apk_version
    }
    save_tokens(tokens, sha, f"Token for {telegram_id}")
    
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
    
    tokens, tokens_sha = load_tokens()
    token_data = tokens.get(token)
    
    if not token_data or token_data['status'] != 'pending':
        return jsonify({"error": "Invalid token"}), 400
    
    if not add_to_allowed_list(android_id):
        return jsonify({"error": "Failed to add"}), 500
    
    token_data['status'] = 'used'
    token_data['used_at'] = datetime.now().isoformat()
    token_data['android_id'] = android_id
    save_tokens(tokens, tokens_sha, f"Token {token} used")
    
    return jsonify({"ok": True})

# ==================== HEALTH ====================

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    logger.info(f"🚀 Запуск на порту {PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG)
