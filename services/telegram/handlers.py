import random
import string
from datetime import datetime, timedelta
import re
from models import User, NotificationSetting, db, AuthCode
from .bot import get_bot

def normalize_phone(phone: str) -> str:
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('0') and len(digits) == 10:
        digits = '38' + digits
    if digits.startswith('380') and len(digits) == 12:
        digits = '+' + digits
    if digits.startswith('38') and len(digits) == 12:
        digits = '+' + digits
    return digits if digits.startswith('+') else '+' + digits

def generate_bind_code():
    return ''.join(random.choices(string.digits, k=6))

def handle_webhook(update):
    print(f"[HANDLER] Отримано update: {update}")
    if "message" not in update:
        return
    message = update["message"]
    chat_id = str(message["chat"]["id"])
    bot = get_bot()
    if not bot:
        print("[HANDLER] Бот не ініціалізовано")
        return

    # Обробка натискання кнопки "Поділитися номером"
    if "contact" in message:
        contact = message["contact"]
        phone = normalize_phone(contact.get("phone_number"))
        if not phone:
            bot.send_message(chat_id, "❌ Не вдалося отримати номер. Спробуйте ще раз.")
            return
        # Генеруємо код
        code = generate_bind_code()
        # Видаляємо старі невикористані коди для цього номера
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
        bot.send_message(chat_id, f"🔐 Ваш код: {code}\nВведіть його на сайті VetFuture для входу.")
        print(f"[HANDLER] Код {code} для номера {phone} збережено")
        return

    text = message.get("text", "")

    # Команда /start
    if text == "/start":
        # Перевіряємо, чи цей chat_id вже прив'язаний до користувача
        existing = NotificationSetting.query.filter_by(channel="telegram", contact=chat_id, is_active=True).first()
        if existing:
            user = User.query.get(existing.user_id)
            if user:
                bot.send_message(chat_id, f"✅ Ви вже зареєстровані як {user.phone}.\nЩоб увійти на сайт, просто введіть ваш номер у формі входу – код прийде сюди автоматично.\nЯкщо хочете отримати новий код, використайте /code.")
            else:
                bot.send_message(chat_id, "✅ Ви вже прив'язали Telegram. Використовуйте сайт для входу.")
        else:
            keyboard = {
                "keyboard": [[{"text": "📱 Поділитися номером", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            bot.send_message(
                chat_id,
                "Для реєстрації або входу, натисніть кнопку нижче, щоб поділитися номером телефону.",
                reply_markup=keyboard
            )
        return

    # Команда /code (отримати новий код, якщо вже прив'язаний)
    if text == "/code":
        existing = NotificationSetting.query.filter_by(channel="telegram", contact=chat_id, is_active=True).first()
        if not existing:
            bot.send_message(chat_id, "Спочатку натисніть /start та поділіться номером.")
            return
        user = User.query.get(existing.user_id)
        if user:
            code = generate_bind_code()
            AuthCode.query.filter_by(phone=user.phone, used=False).delete()
            auth_code = AuthCode(
                phone=user.phone,
                code=code,
                chat_id=chat_id,
                expires_at=datetime.utcnow() + timedelta(minutes=10),
                used=False
            )
            db.session.add(auth_code)
            db.session.commit()
            bot.send_message(chat_id, f"🔐 Ваш новий код: {code}\nВведіть його на сайті.")
        else:
            bot.send_message(chat_id, "Помилка. Спробуйте /start спочатку.")
        return

    # Команда /help
    if text == "/help":
        bot.send_message(chat_id, "/start – початок\n/code – отримати новий код (якщо ви вже зареєстровані)\n/status – перевірити статус прив'язки")
        return

    # Команда /status
    if text == "/status":
        setting = NotificationSetting.query.filter_by(channel="telegram", contact=chat_id, is_active=True).first()
        if setting:
            user = User.query.get(setting.user_id)
            if user:
                bot.send_message(chat_id, f"✅ Telegram прив'язано до акаунту {user.phone}")
            else:
                bot.send_message(chat_id, "❌ Користувача не знайдено")
        else:
            bot.send_message(chat_id, "❌ Telegram не прив'язано. Надішліть /start, поділіться номером та введіть код на сайті.")
        return

    # Підтримка ручного введення номера (якщо користувач вводить номер напряму)
    phone = normalize_phone(text.strip())
    if phone.startswith('+380') and len(phone) == 13:
        # Перевіряємо, чи не прив'язаний уже цей номер до цього чату
        existing = NotificationSetting.query.filter_by(channel="telegram", contact=chat_id, is_active=True).first()
        if existing and existing.user:
            bot.send_message(chat_id, "Ви вже зареєстровані. Використайте /code для отримання нового коду.")
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
        return

    # Невідома команда
    bot.send_message(chat_id, "Невідома команда. Натисніть /start для початку.")