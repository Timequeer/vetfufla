import requests
from datetime import date, timedelta
from flask import Blueprint, render_template, session, redirect, jsonify, request
from models import User, db
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
    visits = enote.get_visits_by_owner(user.enote_guid)
    return jsonify(visits)

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

@client_bp.route('/api/schedule')
def api_schedule():
    data = enote.get_schedule()
    return jsonify(data)

@client_bp.route('/online-appointment')
def online_appointment():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("schedule.html", user=User.query.get(session["user_id"]))

@client_bp.route('/test-api-url')
def test_api_url():
    if not enote.api_key:
        return jsonify({"error": "ENOTE_API_KEY not set"})

    endpoints_to_try = [
        f"{enote.base_url}/enote9991/hs/api/v2",
        f"{enote.base_url}/{enote.clinic_guid}/hs/api/v2",
        f"{enote.base_url}/api/v2",
    ]

    results = {}
    headers = {'apikey': enote.api_key}
    for url in endpoints_to_try:
        try:
            r = requests.get(f"{url}/clients?phone_number=%2B380685442567", headers=headers, timeout=15)
            results[url] = {
                "status": r.status_code,
                "preview": r.text[:200]
            }
        except Exception as e:
            results[url] = {"error": str(e)}

    return jsonify(results)

@client_bp.route('/test-api')
def test_api():
    if not enote.api_key:
        return jsonify({"error": "No API Key"})

    clients, _ = enote._api_get_page('clients', {'phone_number': '+380685442567', 'page_size': 1})
    client = clients[0] if clients else None
    client_id = client.get('id') if client else None

    patients, _ = enote._api_get_page('patients', {'page_size': 10})

    return jsonify({
        "client": client,
        "client_id": client_id,
        "patients_sample": patients[:5],
        "owner_ids_in_sample": [p.get('ownerId') for p in patients[:5]]
    })

@client_bp.route('/debug-schedule')
def debug_schedule():
    date_str = request.args.get('date', date.today().isoformat())
    entity_id = enote.get_entity_id()
    doctors = enote.get_doctors_list()
    if not doctors:
        return jsonify({'error': 'no doctors'})
    emp_id = doctors[0]['id']
    raw = enote.debug_raw('bookings/available_slots', {
        'date': date_str,
        'entity_id': entity_id,
        'employee_id': emp_id
    })
    return jsonify(raw)

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
