from flask import Flask, render_template, request, jsonify
from config import Config
from models import db
from routes.auth import auth_bp
from routes.client import client_bp
from routes.doctor import doctor_bp
from routes.api import api_bp
from routes.admin import admin_bp
from services.notification_service import start_scheduler
from services.telegram.bot import init_bot
from services.telegram.handlers import handle_webhook
import traceback

app = Flask(__name__)
app.config.from_object(Config)
app.config["SQLALCHEMY_DATABASE_URI"] = Config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = Config.SECRET_KEY

db.init_app(app)

# Ініціалізація Telegram бота
init_bot(Config.TELEGRAM_BOT_TOKEN)

# Реєстрація всіх Blueprint
app.register_blueprint(auth_bp)
app.register_blueprint(client_bp)
app.register_blueprint(doctor_bp)
app.register_blueprint(api_bp)
app.register_blueprint(admin_bp)

# ---------- ВСІ МАРШРУТИ ----------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    print("[WEBHOOK] Request received")
    try:
        update = request.get_json()
        print(f"[WEBHOOK] Update: {update}")
        handle_webhook(update)
        return "ok", 200
    except Exception as e:
        print("[WEBHOOK] ❌ ERROR:")
        traceback.print_exc()
        # Важливо: завжди повертаємо 200, щоб Telegram не повторював
        return "ok", 200

@app.route('/webhook', methods=['GET'])
def webhook_test():
    return "Webhook endpoint works! Send POST requests here.", 200

# Запуск планувальника нагадувань
start_scheduler(app)

# ---------- ЗАПУСК СЕРВЕРА ----------
with app.app_context():
    db.create_all()
    print("✅ Таблиці створено або вже існують")

if __name__ == "__main__":
    app.run(debug=True, port=5000)