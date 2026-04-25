import random
import string
from datetime import datetime, timedelta
import re
from models import User, NotificationSetting, db, AuthCode
from .bot import get_bot

# Словник для зберігання стану діалогу (очікування номера)
user_states = {}

def normalize_phone(phone: str) -> str:
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('0') and len(digits) == 10:
        digits = '38' + digits
    if digits.startswith('380') and len(digits) == 12:
        digits = '+' + digits
    if digits.startswith('38') and len(digits) == 12:
        digits = '+' + digits
    return digits

def generate_bind_code():
    return ''.join(random.choices(string.digits, k=6))

def handle_webhook(update):
    print(f"[HANDLER] Отримано update: {update}")
    if "message" not in update:
        return
    message = update["message"]
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "")
    bot = get_bot()
    if not bot:
        print("[HANDLER] Бот не ініціалізовано")
        return

    # Якщо користувач уже чекає на введення номера (після /start)
    if user_states.get(chat_id) == "awaiting_phone":
        phone = normalize_phone(text.strip())
        if not (phone.startswith('+380') and len(phone) == 13):
            bot.send_message(chat_id, "❌ Будь ласка, введіть номер у форматі +380XXXXXXXXX")
            return
        code = generate_bind_code()
        AuthCode.query.filter_by(phone=phone, used=False).delete()
        auth_code = AuthCode(
            phone=phone,
            code=code,
            chat_id=chat_id,
            expires_at=datetime.utcnow() + timedelta(minutes=10),
            used=False
        )
        db.session.add(auth_code)
        db.session.commit()
        bot.send_message(chat_id, f"🔐 Ваш код: {code}\nВведіть його на сайті.")
        print(f"[HANDLER] Код {code} для номера {phone} збережено")
        user_states.pop(chat_id, None)
        return

    # Команда /start
    if text == "/start":
        user_states[chat_id] = "awaiting_phone"
        bot.send_message(chat_id, "Введіть ваш номер телефону у форматі +380XXXXXXXXX")
        return

    # Інші команди...