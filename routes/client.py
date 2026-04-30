from flask import Blueprint, render_template, session, redirect, jsonify
from models import User
from services.enote_service import enote

client_bp = Blueprint('client', __name__)

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
    pets = enote.get_pets_by_owner(user.enote_guid)
    return jsonify(pets)

@client_bp.route('/api/my-analyses')
def my_analyses():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    
    # Один запит замість N по кожній тварині
    pets = enote.get_pets_by_owner(user.enote_guid)
    pet_names = {p['Ref_Key']: p.get('Description', '') for p in pets}
    
    analyses = enote.get_analyses_by_owner(user.enote_guid)
    for a in analyses:
        a['_pet_name'] = pet_names.get(a.get('Карточка_Key', ''), '')
    
    return jsonify(analyses)

@client_bp.route('/api/my-visits')
def my_visits():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    
    pets = enote.get_pets_by_owner(user.enote_guid)  # вже закешовано
    all_visits = []
    for pet in pets:
        visits = enote.get_visits_by_pet(pet['Ref_Key'])
        for v in visits:
            v['_pet_name'] = pet.get('Description', '')
            all_visits.append(v)
    
    # Сортуємо по даті, найновіші першими
    all_visits.sort(key=lambda x: x.get('Date', ''), reverse=True)
    return jsonify(all_visits)

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

@client_bp.route('/api/my-appointments')
def my_appointments():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    appointments = enote.get_appointments_by_owner(user.enote_guid)
    return jsonify(appointments)

@client_bp.route('/api/clear-cache')
def clear_cache():
    enote.clear_cache()
    return jsonify({"message": "Кеш очищено"})

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
