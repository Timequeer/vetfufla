from flask import Flask, jsonify, request, session, render_template, redirect
from config import Config
from models import db, User, AuthCode, NotificationSetting, UserPet
from datetime import datetime, timedelta
import random
import string
from enote_client import ENoteClient
from ai_support import ask_gpt_client, ask_gpt_doctor
from telegram_bot import handle_telegram_update, set_webhook, send_telegram_message
from notifications import start_scheduler

app = Flask(__name__)
app.config.from_object(Config)
app.config["SQLALCHEMY_DATABASE_URI"] = Config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = Config.SECRET_KEY

db.init_app(app)

enote_client = ENoteClient(
    base_url=Config.ENOTE_BASE_URL,
    login=Config.ENOTE_LOGIN,
    password=Config.ENOTE_PASSWORD
)

start_scheduler(app)

# ---------- Утиліти ----------
def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

def send_code_to_user(phone: str, code: str, channel: str = "sms"):
    """
    Відправляє код підтвердження через обраний канал.
    channel: 'telegram' або 'sms'
    """
    if channel == "telegram":
        from models import NotificationSetting
        from notifications import send_notification_to_user
        user = User.query.filter_by(phone=phone).first()
        if user:
            setting = NotificationSetting.query.filter_by(
                user_id=user.id, channel="telegram", is_active=True
            ).first()
            if setting and setting.contact:
                msg = (
                    f"🔐 <b>Код підтвердження VetFuture</b>\n\n"
                    f"Ваш код: <b>{code}</b>\n\n"
                    f"Дійсний 5 хвилин. Нікому не повідомляйте."
                )
                send_telegram_message(setting.contact, msg)
                return
        # Якщо Telegram не знайдено — fallback на print
        print(f"[DEV] Telegram код для {phone}: {code}")
    else:
        # TODO: підключити реальний SMS-сервіс (наприклад, Twilio або LifeCell API)
        print(f"[DEV] SMS код для {phone}: {code}")

# ---------- Маршрути ----------
@app.route("/")
def index():
    return render_template("index.html")  # ← головна сторінка клініки

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    user = User.query.get(session["user_id"])
    if user.is_doctor:
        return redirect("/doctor")
    return render_template("dashboard.html")

@app.route("/doctor")
def doctor_panel():
    if "user_id" not in session:
        return redirect("/login")
    user = User.query.get(session["user_id"])
    if not user.is_doctor:
        return redirect("/dashboard")
    return render_template("doctor.html")

# ---------- Авторизація ----------
@app.route("/api/auth/send-code", methods=["POST"])
def send_code():
    data = request.get_json()
    phone = data.get("phone")
    channel = data.get("channel", "sms")  # 'telegram' або 'sms'
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
    send_code_to_user(phone, code, channel)
    return jsonify({"message": "Код відправлено", "channel": channel}), 200

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

    # Список лікарів — краще перенести в БД або Config
    reserved_doctors = Config.DOCTOR_PHONES if hasattr(Config, 'DOCTOR_PHONES') else []
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

# ---------- ENOTE ----------
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

# ---------- AI підтримка (дві ролі) ----------
@app.route("/api/ai-support", methods=["POST"])
def ai_support():
    """Для власників тварин — загальна консультація."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    data = request.get_json()
    question = data.get("question")
    history = data.get("history", [])  # [{role, content}, ...]
    if not question:
        return jsonify({"error": "Задайте питання"}), 400
    answer = ask_gpt_client(question, history)
    return jsonify({"answer": answer})

@app.route("/api/ai-doctor", methods=["POST"])
def ai_doctor():
    """Для лікарів — клінічний помічник: препарати, дозування, протоколи."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user.is_doctor:
        return jsonify({"error": "Доступ лише для лікарів"}), 403
    data = request.get_json()
    question = data.get("question")
    history = data.get("history", [])
    if not question:
        return jsonify({"error": "Задайте питання"}), 400
    answer = ask_gpt_doctor(question, history)
    return jsonify({"answer": answer})

# ---------- Telegram Webhook ----------
@app.route(f"/webhook/{Config.TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    handle_telegram_update(update, app)
    return "ok"

# ---------- Запуск ----------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("✅ Таблиці створено")
    app.run(debug=True, port=5000)
