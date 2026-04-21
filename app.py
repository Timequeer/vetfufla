from flask import Flask, jsonify, request, session, render_template, redirect
from config import Config
from models import db, User, AuthCode, NotificationSetting, UserPet
from datetime import datetime, timedelta
import random
import string
from enote_client import ENoteClient
from ai_support import ask_gpt
from telegram_bot import handle_telegram_update, set_webhook, send_telegram_message
from notifications import start_scheduler

app = Flask(__name__)
app.config.from_object(Config)
app.config["SQLALCHEMY_DATABASE_URI"] = Config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = Config.SECRET_KEY

db.init_app(app)

# Ініціалізація клієнта ENOTE
enote_client = ENoteClient(
    base_url=Config.ENOTE_BASE_URL,
    login=Config.ENOTE_LOGIN,
    password=Config.ENOTE_PASSWORD
)

# Запуск планувальника сповіщень
start_scheduler(app)

# ---------- Утиліти ----------
def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

def send_code_to_user(phone: str, code: str):
    # TODO: реальне відправлення через Telegram/SMS
    print(f"[DEV] Код для {phone}: {code}")

# ---------- Маршрути авторизації ----------
@app.route("/")
def index():
    return render_template("login.html")

@app.route("/api/auth/send-code", methods=["POST"])
def send_code():
    data = request.get_json()
    phone = data.get("phone")
    if not phone:
        return jsonify({"error": "Вкажіть номер телефону"}), 400
    code = generate_code()
    auth_code = AuthCode(
        phone=phone,
        code=code,
        expires_at=datetime.now() + timedelta(minutes=5)
    )
    db.session.add(auth_code)
    db.session.commit()
    send_code_to_user(phone, code)
    return jsonify({"message": "Код відправлено"}), 200

@app.route("/api/auth/verify-code", methods=["POST"])
def verify_code():
    data = request.get_json()
    phone = data.get("phone")
    code = data.get("code")
    auth_code = AuthCode.query.filter_by(phone=phone, code=code, used=False).first()
    if not auth_code:
        return jsonify({"error": "Невірний код"}), 401
    if datetime.now() > auth_code.expires_at:
        return jsonify({"error": "Код застарів, запросіть новий"}), 401
    auth_code.used = True
    db.session.commit()

    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone)
        db.session.add(user)
        db.session.commit()

    reserved_doctors = ["+380666365496"]   # номери лікарів
    if phone in reserved_doctors:
        user.is_doctor = True
        db.session.commit()

    session["user_id"] = user.id
    return jsonify({
        "message": "Успішний вхід",
        "user": {
            "id": user.id,
            "phone": user.phone,
            "is_doctor": user.is_doctor
        }
    }), 200

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Вихід виконано"}), 200

@app.route("/api/me", methods=["GET"])
def get_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    return jsonify({
        "id": user.id,
        "phone": user.phone,
        "email": user.email,
        "is_doctor": user.is_doctor,
        "enote_guid": user.enote_guid
    }), 200

# ---------- Налаштування сповіщень ----------
@app.route("/api/notifications/settings", methods=["GET", "POST"])
def notification_settings():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    if request.method == "GET":
        settings = NotificationSetting.query.filter_by(user_id=user_id).all()
        return jsonify([{
            "id": s.id,
            "channel": s.channel,
            "contact": s.contact,
            "is_active": s.is_active
        } for s in settings])
    if request.method == "POST":
        data = request.get_json()
        channel = data.get("channel")
        contact = data.get("contact")
        if channel not in ["telegram", "email", "viber"]:
            return jsonify({"error": "Невідомий канал"}), 400
        setting = NotificationSetting(user_id=user_id, channel=channel, contact=contact)
        db.session.add(setting)
        db.session.commit()
        return jsonify({"message": "Збережено"}), 201

# ---------- Робота з ENOTE ----------
@app.route("/api/pets", methods=["GET"])
def get_pets():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user.enote_guid:
        return jsonify({"error": "Клієнт не прив'язаний до Енота"}), 400
    if user.is_doctor:
        pets = enote_client.get_pets_by_doctor_guid(user.enote_guid)
    else:
        pets = enote_client.get_pets_by_owner_guid(user.enote_guid)
    return jsonify(pets)

@app.route("/api/appointments", methods=["GET"])
def get_appointments():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if user.is_doctor:
        appointments = enote_client.get_appointments(doctor_guid=user.enote_guid)
    else:
        pets = enote_client.get_pets_by_owner_guid(user.enote_guid)
        appointments = []
        for pet in pets:
            appointments.extend(enote_client.get_appointments(pet_guid=pet["guid"]))
    return jsonify(appointments)

@app.route("/api/lab-results/<pet_guid>", methods=["GET"])
def get_lab_results(pet_guid):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    results = enote_client.get_lab_results(pet_guid)
    return jsonify(results)

@app.route("/api/vaccinations/<pet_guid>", methods=["GET"])
def get_vaccinations(pet_guid):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    vax = enote_client.get_vaccinations(pet_guid)
    return jsonify(vax)

# ---------- AI підтримка ----------
@app.route("/api/ai-support", methods=["POST"])
def ai_support():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    data = request.get_json()
    question = data.get("question")
    if not question:
        return jsonify({"error": "Задайте питання"}), 400
    answer = ask_gpt(question)
    return jsonify({"answer": answer})

# ---------- Telegram Webhook ----------
@app.route(f"/webhook/{Config.TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    handle_telegram_update(update, app)
    return "ok"

# ---------- Сторінки (HTML) ----------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/")
    user = User.query.get(session["user_id"])
    if user.is_doctor:
        return redirect("/doctor")
    return render_template("dashboard.html")

@app.route("/doctor")
def doctor_panel():
    if "user_id" not in session:
        return redirect("/")
    user = User.query.get(session["user_id"])
    if not user.is_doctor:
        return redirect("/dashboard")
    return render_template("doctor.html")

@app.route("/login")
def login_page():
    return render_template("login.html")
    
# ---------- Запуск ----------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("✅ Таблиці створено")
    app.run(debug=True, port=5000)
    