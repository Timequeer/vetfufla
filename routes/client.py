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

@client_bp.route('/api/my-analyses')
def my_analyses():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    return jsonify(enote.get_analyses_by_owner(user.enote_guid))

    from services.enote_service import enote
    pets = enote.get_pets_by_owner(user.enote_guid)
    if not pets:
        return jsonify({"debug": "немає тварин"})

    # Примусово викликаємо метод, який заповнює _all_analyses
    analyses = enote.get_analyses_by_owner_via_pets(user.enote_guid)

    # Отримуємо доступ до внутрішнього списку
    all_analyses = getattr(enote, '_all_analyses', None)
    total_loaded = len(all_analyses) if all_analyses else 0

    first_pet = pets[0]
    sample_analyses = []
    if all_analyses:
        # Беремо перші 3 аналізи для прикладу
        sample_analyses = all_analyses[:3]

    return jsonify({
        "owner_guid": user.enote_guid,
        "total_pets": len(pets),
        "first_pet_ref": first_pet.get('Ref_Key'),
        "first_pet_name": first_pet.get('Description'),
        "total_analyses_loaded": total_loaded,
        "sample_analyses_keys": [a.get('Карточка_Key') for a in sample_analyses],
        "sample_analyses_desc": [a.get('Description','') for a in sample_analyses],
        "found_analyses_count": len(analyses) if analyses else 0
    })
    
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

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
