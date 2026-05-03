from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from models import db, User, AuthCode, NotificationSetting
from datetime import datetime, timedelta
import random
import string
import re
import time
from services.logger_service import log_action
from services.telegram import get_bot
from services.enote_service import enote


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

      # Автоматическая привязка ENOTE GUID (если ещё не привязан)
    if not user.enote_guid:
        client = enote.find_client_by_phone(phone)
        if client:
            user.enote_guid = client['Ref_Key']
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
from flask import Blueprint, request, jsonify, session
from models import db, User, NotificationSetting
from services.ai_service import ask_gpt
from config import Config
from datetime import datetime
from models import AuthCode
from services.enote_service import enote  # <-- новый импорт (без ENoteClient!)

api_bp = Blueprint('api', __name__)


# Список тварин (тепер через enote, з новими методами)
@api_bp.route('/api/pets', methods=['GET'])
def get_pets():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user.enote_guid:
        return jsonify({"error": "Клієнт не прив'язаний до Енота"}), 400
    if user.is_doctor:
        # Для лікаря поки що повертаємо порожній список (метод get_pets_by_doctor_guid не реалізовано)
        return jsonify([])
    else:
        pets = enote.get_pets_by_owner(user.enote_guid)
    return jsonify(pets)


# Записи на прийом (тимчасово – через візити)
@api_bp.route('/api/appointments', methods=['GET'])
def get_appointments():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if user.is_doctor:
        # Для лікаря поки що повертаємо порожній список
        return jsonify([])
    else:
        # Використовуємо візити замість записів
        visits = enote.get_visits_by_owner(user.enote_guid)
        return jsonify(visits)


# Результати аналізів (тимчасово – через get_analyses_by_pet)
@api_bp.route('/api/lab-results/<pet_guid>', methods=['GET'])
def get_lab_results(pet_guid):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    analyses = enote.get_analyses_by_pet(pet_guid)
    return jsonify(analyses)


# Прививки (поки що не реалізовано в новому сервісі – повертаємо порожній список)
@api_bp.route('/api/vaccinations/<pet_guid>', methods=['GET'])
def get_vaccinations(pet_guid):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    # TODO: додати метод get_vaccinations_by_pet у EnoteClient
    return jsonify([])


# AI-підтримка (без змін)
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


# Налаштування сповіщень (без змін)
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
@api_bp.route('/api/my-phones', methods=['GET'])
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

@api_bp.route('/api/my-phones', methods=['POST'])
def add_phone():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    data = request.get_json()
    phone = data.get("phone")
    comment = data.get("comment", "")
    if not phone:
        return jsonify({"error": "Номер телефону обов'язковий"}), 400
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

@api_bp.route('/api/my-phones/<int:phone_id>', methods=['PUT'])
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

@api_bp.route('/api/my-phones/<int:phone_id>', methods=['DELETE'])
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

@auth_bp.route('/api/resync-enote')
def resync_enote():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Не знайдено"}), 404
    # Скидаємо старий guid і шукаємо заново
    user.enote_guid = None
    db.session.commit()
    new_guid = enote.get_client_by_phone(user.phone)
    if new_guid:
        user.enote_guid = new_guid
        db.session.commit()
        enote.clear_cache()
        return jsonify({"ok": True, "new_guid": new_guid})
    return jsonify({"ok": False, "message": "Не знайдено в ENOTE"})
    
@auth_bp.route('/api/fix-enote')
def fix_enote():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Користувача не знайдено"}), 404
    # Берём GUID из параметра запроса, если передан
    guid = request.args.get('guid')
    if guid:
        user.enote_guid = guid.strip()
        db.session.commit()
        return jsonify({"message": "GUID оновлено", "enote_guid": user.enote_guid})
    else:
        return jsonify({"error": "Не передано параметр guid. Пример: /api/fix-enote?guid=ТВОЙ_GUID"}), 400

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect('/')
