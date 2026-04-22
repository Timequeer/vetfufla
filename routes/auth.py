from flask import Blueprint, render_template, request, jsonify, session
from models import db, User, AuthCode
from datetime import datetime, timedelta
import random
import string
from services.logger_service import log_action

auth_bp = Blueprint('auth', __name__)

def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

def send_code_to_user(phone: str, code: str):
    print(f"[DEV] Код для {phone}: {code}")

# Сторінка логіну
@auth_bp.route('/login')
def login_page():
    return render_template('login.html')

# Надсилання коду
@auth_bp.route('/api/auth/send-code', methods=['POST'])
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

# Перевірка коду
@auth_bp.route('/api/auth/verify-code', methods=['POST'])
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
        user = User(phone=phone, is_doctor=False, is_verified=False)
        db.session.add(user)
        db.session.commit()
        print(f"[INFO] Створено нового користувача: {phone}")
    else:
        print(f"[INFO] Існуючий користувач: {phone}, is_doctor={user.is_doctor}, is_verified={user.is_verified}")

    session["user_id"] = user.id
    session.permanent = True
    
    # ✅ Логуємо успішний вхід (ТУТ - ПІСЛЯ ТОГО, ЯК user ВИЗНАЧЕНО)
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

# Вихід
@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    user_id = session.get("user_id")
    phone = None
    
    if user_id:
        user = User.query.get(user_id)
        if user:
            phone = user.phone
            # ✅ Логуємо вихід (до очищення сесії)
            log_action(user.id, phone, "Вихід з системи", "logout")
    
    session.clear()
    return jsonify({"message": "Вихід виконано"}), 200

# Дані поточного користувача
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

# Захищений ендпоінт для призначення лікаря
@auth_bp.route('/api/admin/make-doctor', methods=['POST'])
def make_doctor():
    from config import Config
    
    data = request.get_json()
    phone = data.get("phone")
    secret = data.get("secret")
    
    if secret != Config.ADMIN_SECRET:
        return jsonify({"error": "Невірний секретний код"}), 403
    
    if not phone:
        return jsonify({"error": "Вкажіть номер телефону"}), 400
    
    user = User.query.filter_by(phone=phone).first()
    if not user:
        return jsonify({"error": "Користувача з таким номером не знайдено"}), 404
    
    user.is_doctor = True
    user.is_verified = True
    db.session.commit()
    
    # ✅ Логуємо призначення лікаря
    log_action(user.id, user.phone, "Призначений лікарем (адміном)", "make_doctor")
    
    return jsonify({
        "message": f"Користувач {phone} тепер лікар",
        "user": {
            "phone": user.phone,
            "is_doctor": user.is_doctor,
            "is_verified": user.is_verified
        }
    }), 200

@auth_bp.route('/api/telegram/link', methods=['POST'])
def link_telegram():
    """Прив'язує Telegram chat_id до користувача"""
    from services.logger_service import log_action
    
    data = request.get_json()
    chat_id = str(data.get("chat_id"))
    phone = data.get("phone")
    code = data.get("code")
    
    if not chat_id or not phone or not code:
        return jsonify({"error": "Вкажіть chat_id, телефон та код"}), 400
    
    # Перевіряємо код
    auth_code = AuthCode.query.filter_by(phone=phone, code=code, used=False).first()
    if not auth_code:
        return jsonify({"error": "Невірний код"}), 401
    if datetime.now() > auth_code.expires_at:
        return jsonify({"error": "Код застарів"}), 401
    
    auth_code.used = True
    db.session.commit()
    
    # Знаходимо або створюємо користувача
    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone)
        db.session.add(user)
        db.session.commit()
    
    # Зберігаємо Telegram chat_id
    setting = NotificationSetting.query.filter_by(
        user_id=user.id, 
        channel="telegram"
    ).first()
    
    if not setting:
        setting = NotificationSetting(
            user_id=user.id,
            channel="telegram",
            contact=chat_id,
            is_active=True
        )
        db.session.add(setting)
    else:
        setting.contact = chat_id
        setting.is_active = True
    
    db.session.commit()
    
    # Надсилаємо привітання в Telegram
    bot = get_bot()
    if bot:
        bot.send_message(chat_id, f"""
✅ <b>Telegram успішно прив'язано!</b>

Ваш акаунт: {phone}
Роль: {"Лікар" if user.is_doctor else "Клієнт"}

Тепер ви отримуватимете коди підтвердження та сповіщення прямо сюди.
        """)
    
    log_action(user.id, phone, f"Прив'язав Telegram (chat_id={chat_id})", "link_telegram")
    
    return jsonify({"message": "Telegram успішно прив'язано!"}), 200