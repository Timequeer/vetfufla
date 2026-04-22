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

# ---------- ВСІ МАРШРУТИ ПОВИННІ БУТИ ТУТ (ПЕРЕД ЗАПУСКОМ) ----------

# Головна сторінка
@app.route('/')
def index():
    return render_template('index.html')

# Webhook для Telegram бота
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    try:
        update = request.get_json()
        print(f"[WEBHOOK] Отримано: {update}")
        
        # Викликаємо обробник
        handle_webhook(update)
        
        return jsonify({"status": "ok", "message": "Webhook received"}), 200
    except Exception as e:
        print(f"[WEBHOOK] Помилка: {e}")
        return jsonify({"status": "error"}), 500

# Тестовий маршрут для перевірки вебхука
@app.route('/webhook', methods=['GET'])
def webhook_test():
    return "Webhook endpoint works! Send POST requests here.", 200

# Запуск планувальника нагадувань
start_scheduler(app)

# ---------- ЗАПУСК СЕРВЕРА ----------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("✅ Таблиці створено")
        print("✅ Telegram бот готовий")
        print("✅ Сервер запускається...")
    app.run(debug=True, port=5000)