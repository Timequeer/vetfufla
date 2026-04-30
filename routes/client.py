from flask import Blueprint, render_template, session, redirect, jsonify
from models import User
from services.enote_service import enote
import time
import logging

client_bp = Blueprint('client', __name__)

# Простий кеш у пам'яті для аналізів (на майбутнє)
_analyses_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 30 * 60  # 30 хвилин
}

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

@client_bp.route('/api/clear-cache')
def clear_cache():
    enote.clear_cache()
    global _analyses_cache
    _analyses_cache = {"data": None, "timestamp": 0, "ttl": 30 * 60}
    return jsonify({"message": "Кеш очищено"})

@client_bp.route('/api/test-analyses')
def test_analyses():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])

    # Fallback логіка (тимчасова, для тесту)
    contact = enote.get_contact_by_owner(user.enote_guid)
    if not contact:
        return jsonify({"error": "Контакт не знайдено"}), 404

    contact_guid = contact['Ref_Key']
    url = enote._build_url("Document_Анализы")
    all_analyses = []
    skip = 0
    limit = 2000

    while len(all_analyses) < limit:
        batch = enote._get(url, {"$top": 100, "$skip": skip})
        if not batch:
            break
        for a in batch:
            if a.get('КонтактноеЛицо_Key') == contact_guid:
                all_analyses.append(a)
        skip += 100

    # Додаємо клички тварин
    pets = enote.get_pets_by_owner(user.enote_guid)
    pet_names = {p['Ref_Key']: p.get('Description', '') for p in pets}
    for a in all_analyses:
        a['_pet_name'] = pet_names.get(a.get('Карточка_Key'), '')

    all_analyses.sort(key=lambda x: x.get('Date', ''), reverse=True)
    return jsonify({
        "total_loaded": len(all_analyses),
        "analyses": all_analyses[:50]
    })

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
