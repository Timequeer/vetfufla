from models import User, NotificationSetting, db
from .bot import get_bot

def handle_webhook(update):
    """Обробляє вхідні повідомлення від Telegram"""
    print(f"[HANDLER] Обробка update: {update}")
    
    if "message" not in update:
        return
    
    message = update["message"]
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "")
    
    bot = get_bot()
    if not bot:
        print("[HANDLER] Бот не ініціалізовано")
        return
    
    # Команда /start
    if text == "/start":
        bot.send_message(chat_id, """
🐾 <b>Вітаємо у VetFuture боті!</b>

Цей бот допоможе вам отримувати сповіщення:
• 📅 Нагадування про записи до лікаря
• 💉 Нагадування про вакцинацію

<b>Як прив'язати бота до акаунту:</b>
1. Увійдіть на сайт VetFuture
2. Перейдіть в розділ "Налаштування"
3. Оберіть "Прив'язати Telegram"

<b>Команди:</b>
/start - це повідомлення
/help - допомога
/status - статус підключення
        """)
        return
    
    # Команда /help
    if text == "/help":
        bot.send_message(chat_id, """
❓ <b>Допомога</b>

Щоб отримувати сповіщення, прив'яжіть бота на сайті:
1. Увійдіть на сайт
2. Перейдіть в "Налаштування"
3. Натисніть "Прив'язати Telegram"

Після прив'язки ви отримуватимете:
• Коди для входу
• Нагадування про записи
• Сповіщення про вакцинацію
        """)
        return
    
    # Команда /status
    if text == "/status":
        setting = NotificationSetting.query.filter_by(
            channel="telegram", 
            contact=chat_id, 
            is_active=True
        ).first()
        
        if setting:
            user = User.query.get(setting.user_id)
            if user:
                bot.send_message(chat_id, f"""
✅ <b>Telegram прив'язано!</b>

📱 Ваш акаунт: {user.phone}
👨‍⚕️ Роль: {"Лікар" if user.is_doctor else "Клієнт"}

Ви отримуватимете сповіщення про:
• Записи на прийом
• Ревакцинацію
• Результати аналізів
                """)
            else:
                bot.send_message(chat_id, "❌ Користувача не знайдено")
        else:
            bot.send_message(chat_id, """
❌ <b>Telegram не прив'язано</b>

Для прив'язки:
1. Увійдіть на сайт
2. Перейдіть в налаштування
3. Натисніть "Прив'язати Telegram"
            """)
        return
    
    # Невідома команда
    bot.send_message(chat_id, f"Невідома команда: {text}\nВикористайте /start або /help")