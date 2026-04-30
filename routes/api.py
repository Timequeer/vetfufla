from flask import Blueprint, request, jsonify, session
from models import db, User, NotificationSetting
from services.ai_service import ask_gpt
from config import Config
from datetime import datetime
from models import AuthCode
from services.enote_service import ENoteClient
from config import Config

# Ініціалізація клієнта ENOTE
enote_client = ENoteClient(
    base_url=Config.ENOTE_BASE_URL,
    login=Config.ENOTE_LOGIN,
    password=Config.ENOTE_PASSWORD
)


api_bp = Blueprint('api', __name__)


# Список тварин
@api_bp.route('/api/pets', methods=['GET'])
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

# Записи на прийом
@api_bp.route('/api/appointments', methods=['GET'])
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

# Результати аналізів
@api_bp.route('/api/lab-results/<pet_guid>', methods=['GET'])
def get_lab_results(pet_guid):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    results = enote_client.get_lab_results(pet_guid)
    return jsonify(results)

# Прививки
@api_bp.route('/api/vaccinations/<pet_guid>', methods=['GET'])
def get_vaccinations(pet_guid):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    vax = enote_client.get_vaccinations(pet_guid)
    return jsonify(vax)

# AI-підтримка
@api_bp.route('/api/ai-support', methods=['POST'])
def ai_support():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    user_role = "doctor" if user.is_doctor and user.is_verified else "client"
    
    data = request.get_json()
    question = data.get("question")
    if not question:
        return jsonify({"error": "Задайте питання"}), 400
    
    answer = ask_gpt(question, user_role=user_role)
    return jsonify({"answer": answer})

# Налаштування сповіщень
@api_bp.route('/api/notifications/settings', methods=['GET', 'POST'])
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

# ---------- Telegram прив'язка ----------
@api_bp.route('/api/telegram/status', methods=['GET'])
def telegram_status():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    setting = NotificationSetting.query.filter_by(user_id=user.id, channel="telegram", is_active=True).first()
    return jsonify({
        "connected": setting is not None,
        "phone": user.phone if setting else None
    })

@api_bp.route('/api/telegram/bind', methods=['POST'])
def bind_telegram():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    
    data = request.get_json()
    code = data.get("code")
    if not code:
        return jsonify({"error": "Введіть код"}), 400
    
    # Шукаємо код у таблиці AuthCode (де phone – це chat_id)
    auth_code = AuthCode.query.filter_by(code=code, used=False).first()
    if not auth_code or auth_code.expires_at < datetime.utcnow():
        return jsonify({"error": "Невірний або прострочений код"}), 401
    
    chat_id = auth_code.phone
    auth_code.used = True
    db.session.commit()
    
    user = User.query.get(user_id)
    setting = NotificationSetting.query.filter_by(user_id=user.id, channel="telegram").first()
    if not setting:
        setting = NotificationSetting(user_id=user.id, channel="telegram", contact=chat_id, is_active=True)
        db.session.add(setting)
    else:
        setting.contact = chat_id
        setting.is_active = True
    db.session.commit()
    
    from services.telegram import get_bot
    bot = get_bot()
    if bot:
        bot.send_message(chat_id, f"✅ Telegram прив'язано до акаунту {user.phone}")
    
    return jsonify({"message": "Telegram успішно прив'язано!"}), 200

from models import UserPhone

# ---------- Додаткові номери телефонів ----------
@api_bp.route('/my-phones', methods=['GET'])
def get_my_phones():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    phones = UserPhone.query.filter_by(user_id=user_id).all()
    return jsonify([{
        "id": p.id,
        "phone": p.phone,
        "comment": p.comment
    } for p in phones])

@api_bp.route('/my-phones', methods=['POST'])
def add_phone():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    data = request.get_json()
    phone = data.get("phone")
    comment = data.get("comment", "")
    if not phone:
        return jsonify({"error": "Номер телефону обов'язковий"}), 400
    # Нормалізація номера (можна використати вже існуючу функцію з auth.py, але я продублюю)
    import re
    def normalize_phone(p):
        digits = re.sub(r'\D', '', p)
        if digits.startswith('0') and len(digits) == 10:
            digits = '38' + digits
        if digits.startswith('380') and len(digits) == 12:
            digits = '+' + digits
        if digits.startswith('38') and len(digits) == 12:
            digits = '+' + digits
        return digits if digits.startswith('+') else '+' + digits
    phone = normalize_phone(phone)
    new_phone = UserPhone(user_id=user_id, phone=phone, comment=comment)
    db.session.add(new_phone)
    db.session.commit()
    return jsonify({"id": new_phone.id, "phone": new_phone.phone, "comment": new_phone.comment}), 201

@api_bp.route('/my-phones/<int:phone_id>', methods=['PUT'])
def update_phone(phone_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    phone_entry = UserPhone.query.filter_by(id=phone_id, user_id=user_id).first()
    if not phone_entry:
        return jsonify({"error": "Номер не знайдено"}), 404
    data = request.get_json()
    if "phone" in data:
        phone_entry.phone = data["phone"]
    if "comment" in data:
        phone_entry.comment = data["comment"]
    db.session.commit()
    return jsonify({"id": phone_entry.id, "phone": phone_entry.phone, "comment": phone_entry.comment})

@api_bp.route('/my-phones/<int:phone_id>', methods=['DELETE'])
def delete_phone(phone_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    phone_entry = UserPhone.query.filter_by(id=phone_id, user_id=user_id).first()
    if not phone_entry:
        return jsonify({"error": "Номер не знайдено"}), 404
    db.session.delete(phone_entry)
    db.session.commit()
    return jsonify({"message": "Видалено"}), 200

@api_bp.route('/api/telegram/unbind', methods=['POST'])
def unbind_telegram():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    setting = NotificationSetting.query.filter_by(user_id=user.id, channel="telegram").first()
    if setting:
        setting.is_active = False
        db.session.commit()
    return jsonify({"message": "Telegram відв'язано"}), 200
