import requests

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send_message(self, chat_id, text, parse_mode="HTML", reply_markup=None):
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            response = requests.post(url, json=payload, timeout=10)
            if not response.ok:
                print(f"[TELEGRAM] Помилка: {response.text}")
            return response.ok
        except Exception as e:
            print(f"[TELEGRAM] Виняток: {e}")
            return False

# Глобальний екземпляр
_bot = None

def init_bot(token):
    global _bot
    _bot = TelegramBot(token)
    print("✅ Telegram бот ініціалізовано")
    return _bot

def get_bot():
    return _bot