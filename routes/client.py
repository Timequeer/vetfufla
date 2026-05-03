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
        return jsonify({"phone": user.phone if user else ""})
    profile = enote.get_client_profile(user.enote_guid)
    return jsonify({
        "full_name": profile.get('name', ''),
        "phone": user.phone,
        "email": user.email
    })

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


@client_bp.route('/test-contact-filter')
def test_contact_filter():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No session"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify({"error": "No enote_guid"}), 400

    contact = enote.get_contact_by_owner(user.enote_guid)
    if not contact:
        return jsonify({"error": "No contact found"}), 404

    contact_guid = contact['Ref_Key']
    result = {}

    # Перевіряємо візити
    url_visits = enote._build_url("Document_Посещение")
    r = enote.session.get(url_visits, params={
        "$filter": f"КонтактноеЛицо_Key eq guid'{contact_guid}'",
        "$top": 5,
        "$format": "json"
    }, timeout=25)
    result["visits"] = {"status": r.status_code, "count": len(r.json().get('value', [])) if r.ok else 0, "preview": r.text[:200]}

    # Перевіряємо записи на прийом
    url_app = enote._build_url("Task_ПредварительнаяЗапись")
    r = enote.session.get(url_app, params={
        "$filter": f"КонтактноеЛицо_Key eq guid'{contact_guid}'",
        "$top": 5,
        "$format": "json"
    }, timeout=25)
    result["appointments"] = {"status": r.status_code, "count": len(r.json().get('value', [])) if r.ok else 0, "preview": r.text[:200]}

    # Перевіряємо аналізи
    url_an = enote._build_url("Document_Анализы")
    r = enote.session.get(url_an, params={
        "$filter": f"КонтактноеЛицо_Key eq guid'{contact_guid}'",
        "$top": 5,
        "$format": "json"
    }, timeout=25)
    result["analyses"] = {"status": r.status_code, "count": len(r.json().get('value', [])) if r.ok else 0, "preview": r.text[:200]}

    return jsonify(result)

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
