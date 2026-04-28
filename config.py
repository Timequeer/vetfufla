import os

class Config:
    # База даних – беремо з оточення, для Render це буде PostgreSQL
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///vetfuture.db")
    
    # Секретний ключ Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "змін-цей-ключ-на-рандомний")
    
    # ENOTE API
    ENOTE_BASE_URL = os.getenv("ENOTE_BASE_URL", "")
    ENOTE_LOGIN = os.getenv("ENOTE_LOGIN", "")
    ENOTE_PASSWORD = os.getenv("ENOTE_PASSWORD", "")
    
    # Telegram бот
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_BOT_USERNAME = "VetFurure_bot"
    
    # Email
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    
    # OpenAI API
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # Адміністратори
    ADMIN_PHONES = os.getenv("ADMIN_PHONES", "+380666365496").split(",")
    ADMIN_SECRET = os.getenv("ADMIN_SECRET", "SuperSecret123!")