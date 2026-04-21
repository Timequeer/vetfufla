import os

class Config:
    # --- База даних ---
    DATABASE_URL = "sqlite:///vetfuture.db"  # ← змінив на SQLite
    
    # --- Секретний ключ Flask ---
    SECRET_KEY = os.getenv("SECRET_KEY", "змін-цей-ключ-на-рандомний")
    
    # --- ENOTE API ---
    ENOTE_BASE_URL = os.getenv("ENOTE_BASE_URL", "")
    ENOTE_LOGIN = os.getenv("ENOTE_LOGIN", "")
    ENOTE_PASSWORD = os.getenv("ENOTE_PASSWORD", "")
    
    # --- Telegram бот ---
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # --- Email (Gmail SMTP) ---
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    
    # --- OpenAI API ---
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")