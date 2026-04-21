import requests
from flask import current_app
from models import User, NotificationSetting, db

def set_webhook(app, bot_token, webhook_url):
    """
    Устанавливает вебхук для Telegram бота
    """
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    try:
        resp = requests.post(url, json={"url": webhook_url})
        return resp.ok
    except Exception as e:
        print(f"Ошибка установки вебхука: {e}")
        return False

def handle_telegram_update(update, app):
    """
    Обрабатывает входящие сообщения от Telegram бота
    """
    with app.app_context():
        # Проверяем, есть ли сообщение
        if "message" not in update:
            return
        
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        
        # Обработка команды /start
        if text == "/start":
            send_telegram_message(chat_id, "Вітаю! 👋\n\nВведіть ваш номер телефону для зв'язку з клінікою.\nФормат: +380XXXXXXXXX")
            return
        
        # Пытаемся найти пользователя по номеру телефона
        phone = text.strip()
        
        # Проверяем, что номер имеет правильный формат
        if not phone.startswith('+') or not phone[1:].isdigit():
            send_telegram_message(chat_id, "❌ Будь ласка, введіть номер у форматі +380XXXXXXXXX")
            return
        
        # Ищем пользователя в базе
        user = User.query.filter_by(phone=phone).first()
        
        if user:
            # Проверяем, есть ли уже настройка уведомлений для Telegram
            setting = NotificationSetting.query.filter_by(
                user_id=user.id, 
                channel="telegram"
            ).first()
            
            if not setting:
                # Создаем новую настройку
                setting = NotificationSetting(
                    user_id=user.id, 
                    channel="telegram", 
                    contact=str(chat_id), 
                    is_active=True
                )
                db.session.add(setting)
                message = "✅ Дякуємо! Ви будете отримувати сповіщення про:\n\n• Записи на прийом\n• Ревакцинацію\n• Результати аналізів\n• Важливі новини клініки"
            else:
                # Обновляем существующую настройку
                setting.contact = str(chat_id)
                setting.is_active = True
                message = "🔄 Ваш Telegram підтверджено! Сповіщення активовано."
            
            db.session.commit()
            send_telegram_message(chat_id, message)
        else:
            send_telegram_message(
                chat_id, 
                "❌ Номер не знайдено в системі.\n\n"
                "1. Спочатку зареєструйтесь на сайті\n"
                "2. Потім введіть цей самий номер тут\n\n"
                f"Введений номер: {phone}"
            )

def send_telegram_message(chat_id, text):
    """
    Отправляет сообщение в Telegram
    """
    bot_token = current_app.config.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        print("Telegram bot token not configured")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        response = requests.post(url, json={
            "chat_id": chat_id, 
            "text": text,
            "parse_mode": "HTML"
        }, timeout=5)
        return response.ok
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False

def send_notification_to_user(user_id, message):
    """
    Отправляет уведомление пользователю через Telegram (если настроен)
    """
    with current_app.app_context():
        # Ищем настройки Telegram для пользователя
        setting = NotificationSetting.query.filter_by(
            user_id=user_id, 
            channel="telegram", 
            is_active=True
        ).first()
        
        if setting and setting.contact:
            chat_id = setting.contact
            return send_telegram_message(chat_id, message)
        return False