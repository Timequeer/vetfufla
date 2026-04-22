import requests

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send_message(self, chat_id, text, parse_mode="HTML"):
        """Надсилає повідомлення користувачу"""
        url = f"{self.base_url}/sendMessage"
        try:
            response = requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }, timeout=10)
            return response.ok
        except Exception as e:
            print(f"[TELEGRAM] Помилка відправки: {e}")
            return False
    
    def send_code(self, chat_id, code):
        """Надсилає код підтвердження"""
        text = f"""
🔐 <b>Код підтвердження VetFuture</b>

<b>{code}</b>

Код дійсний 5 хвилин.
        """
        return self.send_message(chat_id, text)


# Глобальний екземпляр бота
_bot = None

def init_bot(token):
    """Ініціалізує глобальний екземпляр бота"""
    global _bot
    _bot = TelegramBot(token)
    print("✅ Telegram бот ініціалізовано")
    return _bot

def get_bot():
    """Повертає глобальний екземпляр бота"""
    return _bot