import requests

def set_webhook(token, url):
    """Встановлює вебхук для бота"""
    response = requests.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": url}
    )
    return response.json()

def delete_webhook(token):
    """Видаляє вебхук"""
    response = requests.post(
        f"https://api.telegram.org/bot{token}/deleteWebhook"
    )
    return response.json()

def get_webhook_info(token):
    """Отримує інформацію про вебхук"""
    response = requests.get(
        f"https://api.telegram.org/bot{token}/getWebhookInfo"
    )
    return response.json()