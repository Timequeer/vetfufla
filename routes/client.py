from flask import Blueprint, render_template, session, redirect, jsonify
from models import User
from services.enote_service import enote
import time
import logging

client_bp = Blueprint('client', __name__)

# Простий кеш у пам'яті для аналізів
_analyses_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 30 * 60  # 30 хвилин
}

def get_cached_analyses(owner_guid):
    logging.info(f"[ANALYSES] Запит для owner_guid={owner_guid}")
    now = time.time()
    if _analyses_cache["data"] is not None and (now - _analyses_cache["timestamp"]) < _analyses_cache["ttl"]:
        logging.info("[ANALYSES] Повертаємо з кешу")
        return _analyses_cache["data"]

    data = enote.get_analyses_by_owner_via_pets(owner_guid)
    logging.info(f"[ANALYSES] Отримано {len(data) if data else 0} записів")
    if not data:
        pets = enote.get_pets_by_owner(owner_guid)
        if pets:
            pet = pets[0]
            logging.info(f"[ANALYSES] Тварина: {pet.get('Description')}, guid={pet['Ref_Key']}")
            url = enote._build_url("Document_Анализы")
            params = {"$format": "json", "$top": 3}
            r = enote.session.get(url, params=params, timeout=90)
            logging.info(f"[ANALYSES] ENOTE status: {r.status_code}, text: {r.text[:200]}")
    _analyses_cache["data"] = data if data else []
    _analyses_cache["timestamp"] = now
    return _analyses_cache["data"]

@client_bp.route('/dashboard')
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    user = User.query.get(session["user_id"])
    if not user:
        return redirect("/login")
    if user.is_doctor:
        return redirect("/doctor")
    return render_template("dashboard.html", user=user)

@client_bp.route('/api/my-pets')
def my_pets():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    return jsonify(enote.get_pets_by_owner(user.enote_guid))

@client_bp.route('/api/my-analyses')
def my_analyses():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    return jsonify(get_cached_analyses(user.enote_guid))

@client_bp.route('/api/my-visits')
def my_visits():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    pets = enote.get_pets_by_owner(user.enote_guid)
    all_visits = []
    for pet in pets:
        visits = enote.get_visits_by_pet(pet['Ref_Key'])
        for v in visits:
            v['_pet_name'] = pet.get('Description', '')
            all_visits.append(v)
    all_visits.sort(key=lambda x: x.get('Date', ''), reverse=True)
    return jsonify(all_visits)

@client_bp.route('/api/my-appointments')
def my_appointments():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    appointments = enote.get_appointments_by_owner(user.enote_guid)
    return jsonify(appointments if appointments else [])

@client_bp.route('/api/my-profile')
def my_profile():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify({})
    contact = enote.get_contact_by_owner(user.enote_guid)
    if contact:
        return jsonify({
            "full_name": f"{contact.get('Фамилия', '')} {contact.get('Имя', '')}".strip(),
            "phone": user.phone,
            "email": user.email
        })
    return jsonify({"phone": user.phone, "email": user.email})

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
