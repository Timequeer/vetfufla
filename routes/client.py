from flask import Blueprint, render_template, session, redirect, jsonify
from models import User
from services.enote_service import enote
import time
import logging

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
    return jsonify(enote.get_pets_by_owner(user.enote_guid))

@client_bp.route('/api/my-analyses')
def my_analyses():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    return jsonify(enote.get_analyses_by_owner(user.enote_guid))

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
    return jsonify({"message": "Кеш очищено"})

@client_bp.route('/test-auth')
def test_auth():
    url = enote._build_url("Catalog_Карточки")
    r = enote.session.get(url, params={"$top": 1, "$format": "json"})
    return jsonify({"status": r.status_code, "body": r.text[:200]})

@client_bp.route('/test-appointments')
def test_appointments():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No session"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify({"error": "No enote_guid"}), 400

    pets = enote.get_pets_by_owner(user.enote_guid)
    result = {}
    for pet in pets[:2]:   # тільки перші дві тварини
        pet_key = pet['Ref_Key']
        url = enote._build_url("Task_ПредварительнаяЗапись")
        params = {
            "$filter": f"Карточка_Key eq guid'{pet_key}'",
            "$top": 3,
            "$format": "json"
        }
        r = enote.session.get(url, params=params, timeout=25)
        result[pet.get('Description', '')] = {
            "status": r.status_code,
            "body": r.json() if r.ok else r.text[:200]
        }

    # так само для візитів (першої тварини)
    first_pet = pets[0] if pets else None
    if first_pet:
        url_visits = enote._build_url("Document_Посещение")
        r_visits = enote.session.get(url_visits, params={
            "$filter": f"Карточка_Key eq guid'{first_pet['Ref_Key']}'",
            "$top": 3,
            "$format": "json"
        }, timeout=25)
        result["visits_for_" + str(first_pet.get('Description', ''))] = {
            "status": r_visits.status_code,
            "body": r_visits.json() if r_visits.ok else r_visits.text[:200]
        }

    return jsonify(result)

@client_bp.route('/online-appointment')
def online_appointment():
    if "user_id" not in session:
        return redirect("/login")
    # Поки що просто відкриваємо сторінку графіка
    return render_template("schedule.html", user=User.query.get(session["user_id"]))

@client_bp.route('/api/schedule')
def api_schedule():
    data = enote.get_schedule()
    return jsonify(data)

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
