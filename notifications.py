import smtplib
from email.mime.text import MIMEText
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from models import User, NotificationSetting, db
from enote_client import ENoteClient

def send_telegram(chat_id, text, bot_token):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")

def send_email(to_email, subject, body, mail_config):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = mail_config["username"]
    msg["To"] = to_email
    try:
        with smtplib.SMTP(mail_config["server"], mail_config["port"]) as server:
            server.starttls()
            server.login(mail_config["username"], mail_config["password"])
            server.send_message(msg)
    except Exception as e:
        print(f"Email error: {e}")

def check_and_notify(app):
    with app.app_context():
        # Получаем всех пользователей с активными уведомлениями
        settings = NotificationSetting.query.filter_by(is_active=True).all()
        # Здесь должна быть логика: для каждого юзера получить его животных из Енота,
        # проверить предстоящие записи (на завтра) и даты ревакцинации.
        # Пока заглушка – просто выводим в консоль
        print(f"[SCHEDULER] Checking notifications for {len(settings)} settings")
        # TODO: реальная проверка через enote_client

def start_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=lambda: check_and_notify(app), trigger="interval", hours=1)
    scheduler.start()