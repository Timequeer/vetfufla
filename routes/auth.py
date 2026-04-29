from flask import Blueprint, render_template, request, jsonify, session
from models import db, User, AuthCode, NotificationSetting
from datetime import datetime, timedelta
import random
import string
import re
import time
from services.logger_service import log_action
from services.telegram import get_bot

auth_bp = Blueprint('auth', __name__)

def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

def normalize_phone(phone: str) -> str:
    if not phone:
        return phone
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('0') and len(digits) == 10:
        digits = '38' + digits
    if digits.startswith('380') and len(digits) == 12:
        digits = '+' + digits
    if phone.startswith('+380') and len(digits) == 13:
        return phone
    if digits.startswith('38') and len(digits) == 12:
        digits = '+' + digits
    return digits

def send_code_to_user(phone: str, code: str):
    print(f"[DEV] Код для {phone}: {code}")
    user = User.query.filter_by(phone=phone).first()
    if user:
        tg_setting = NotificationSetting.query.filter_by(
            user_id=user.id, channel="telegram", is_active=True
        ).first()
        if tg_setting and tg_setting.contact:
            bot = get_bot()
            if bot:
                bot.send_message(tg_setting.contact, f"🔐 Ваш код для входу: {code}")
                print(f"[TELEGRAM] Код надіслано в Telegram для {phone}")
                return
    print(f"[DEV] Код виведено в консоль (Telegram не налаштовано для {phone})")

@auth_bp.route('/login')
def login_page():
    return render_template('login.html')

@auth_bp.route('/api/auth/send-code', methods=['POST'])
def send_code():
    print("=== send_code called ===")
    try:
        data = request.get_json()
    except Exception as e:
        return jsonify({"error": "Неправильний формат запиту"}), 400
    if not data:
        return jsonify({"error": "Відсутні дані"}), 400
    raw_phone = data.get("phone")
    if not raw_phone:
        return jsonify({"error": "Вкажіть номер телефону"}), 400
    phone = normalize_phone(raw_phone)
    print(f"[SEND-CODE] Номер після нормалізації: {phone}")

    # Видаляємо прострочені коди (час UTC)
    AuthCode.query.filter(AuthCode.phone == phone, AuthCode.expires_at < datetime.utcnow()).delete()
    db.session.commit()

    auth_code = AuthCode.query.filter_by(phone=phone, used=False).first()
    print(f"[SEND-CODE] Активний код: {auth_code.code if auth_code else 'None'}")
    if auth_code and auth_code.expires_at > datetime.utcnow():
        print("[SEND-CODE] Активний код є, повертаємо відповідь")
        return jsonify({"message": "Код вже був надісланий. Введіть його."}), 200

    # Якщо коду немає, то перевіряємо, чи користувач зареєстрований і чи має Telegram
    user = User.query.filter_by(phone=phone).first()
    print(f"[SEND-CODE] Користувач: {user.phone if user else 'None'}")
    if user:
        tg_setting = NotificationSetting.query.filter_by(user_id=user.id, channel="telegram", is_active=True).first()
        print(f"[SEND-CODE] Telegram прив'язка: {tg_setting.contact if tg_setting else 'None'}")
        if tg_setting and tg_setting.contact:
            code = generate_code()
            new_code = AuthCode(
                phone=phone,
                code=code,
                expires_at=datetime.utcnow() + timedelta(minutes=5),
                used=False
            )
            db.session.add(new_code)
            db.session.commit()
            bot = get_bot()
            if bot:
                bot.send_message(tg_setting.contact, f"🔐 Ваш код для входу: {code}")
                return jsonify({"message": "Код надіслано в Telegram"}), 200
            else:
                return jsonify({"error": "Помилка бота"}), 500
    # Якщо користувача немає і активного коду теж немає
    return jsonify({"error": "Спочатку отримайте код у Telegram-бота @VetFurure_bot (команда /start, потім введіть номер)"}), 400

@auth_bp.route('/api/auth/verify-code', methods=['POST'])
def verify_code():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Відсутні дані"}), 400
    raw_phone = data.get("phone")
    code = data.get("code")
    if not raw_phone or not code:
        return jsonify({"error": "Вкажіть номер телефону та код"}), 400
    phone = normalize_phone(raw_phone)
    
    # Знаходимо активний код для цього номера
    auth_code = AuthCode.query.filter_by(phone=phone, used=False).first()
    
    if not auth_code:
        time.sleep(1)
        return jsonify({"error": "Невірний або застарілий код"}), 401
    
    # Перевірка блокування за спробами
    if auth_code.attempts >= 3:
        auth_code.used = True
        db.session.commit()
        time.sleep(1)
        return jsonify({"error": "Код заблоковано, запросіть новий"}), 401
    
    # Перевірка часу життя
    if datetime.utcnow() > auth_code.expires_at:
        auth_code.used = True
        db.session.commit()
        time.sleep(1)
        return jsonify({"error": "Невірний або застарілий код"}), 401
    
    # Перевірка власне коду
    if auth_code.code != code:
        auth_code.attempts += 1
        db.session.commit()
        time.sleep(1)
        return jsonify({"error": "Невірний або застарілий код"}), 401
    
    # Успішна верифікація
    auth_code.used = True
    db.session.commit()
    
    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone, is_doctor=False, is_verified=False)
        db.session.add(user)
        db.session.commit()
    
    if auth_code.chat_id:
        setting = NotificationSetting.query.filter_by(user_id=user.id, channel="telegram").first()
        if not setting:
            setting = NotificationSetting(user_id=user.id, channel="telegram", contact=auth_code.chat_id, is_active=True)
            db.session.add(setting)
        else:
            setting.contact = auth_code.chat_id
            setting.is_active = True
        db.session.commit()
    
    session["user_id"] = user.id
    session.permanent = True
    log_action(user.id, user.phone, "Успішний вхід", "verify_code")
    
    return jsonify({
        "message": "Успішний вхід",
        "user": {
            "id": user.id,
            "phone": user.phone,
            "email": user.email,
            "is_doctor": user.is_doctor,
            "is_verified": user.is_verified,
            "enote_guid": user.enote_guid
        }
    }), 200

@auth_bp.route('/api/me', methods=['GET'])
def get_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user:
        session.clear()
        return jsonify({"error": "Користувача не знайдено"}), 401
    return jsonify({
        "id": user.id,
        "phone": user.phone,
        "email": user.email,
        "is_doctor": user.is_doctor,
        "is_verified": user.is_verified,
        "enote_guid": user.enote_guid
    }), 200

@auth_bp.route('/api/admin/make-doctor', methods=['POST'])
def make_doctor():
    from config import Config
    data = request.get_json()
    raw_phone = data.get("phone")
    secret = data.get("secret")
    if secret != Config.ADMIN_SECRET:
        return jsonify({"error": "Невірний секретний код"}), 403
    if not raw_phone:
        return jsonify({"error": "Вкажіть номер телефону"}), 400
    phone = normalize_phone(raw_phone)
    user = User.query.filter_by(phone=phone).first()
    if not user:
        return jsonify({"error": "Користувача з таким номером не знайдено"}), 404
    user.is_doctor = True
    user.is_verified = True
    db.session.commit()
    log_action(user.id, user.phone, "Призначений лікарем (адміном)", "make_doctor")
    return jsonify({
        "message": f"Користувач {phone} тепер лікар",
        "user": {
            "phone": user.phone,
            "is_doctor": user.is_doctor,
            "is_verified": user.is_verified
        }
    }), 200
