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

# ---------- Животные (уже работает) ----------
@client_bp.route('/api/my-pets')
def my_pets():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    all_pets = enote.get_all_pets()
    my_pets = [p for p in all_pets if p.get('Хозяин_Key') == user.enote_guid]
    return jsonify(my_pets)

# ---------- Анализы ----------
@client_bp.route('/api/my-analyses')
def my_analyses():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    all_pets = enote.get_all_pets()
    my_pet_guids = [p['Ref_Key'] for p in all_pets if p.get('Хозяин_Key') == user.enote_guid]
    if not my_pet_guids:
        return jsonify([])
    all_analyses = enote.get_all_analyses()
    my_analyses = [a for a in all_analyses if a.get('Карточка_Key') in my_pet_guids]
    # добавим имя питомца для красивого отображения
    pet_names = {p['Ref_Key']: p.get('Description', '') for p in all_pets}
    for a in my_analyses:
        a['_pet_name'] = pet_names.get(a.get('Карточка_Key'), '')
    return jsonify(my_analyses)

# ---------- История визитов ----------
@client_bp.route('/api/my-visits')
def my_visits():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    all_pets = enote.get_all_pets()
    my_pet_guids = [p['Ref_Key'] for p in all_pets if p.get('Хозяин_Key') == user.enote_guid]
    if not my_pet_guids:
        return jsonify([])
    all_visits = enote.get_all_visits()
    my_visits = [v for v in all_visits if v.get('Карточка_Key') in my_pet_guids]
    pet_names = {p['Ref_Key']: p.get('Description', '') for p in all_pets}
    for v in my_visits:
        v['_pet_name'] = pet_names.get(v.get('Карточка_Key'), '')
    return jsonify(my_visits)

# ---------- Профиль (ФИО) ----------
@client_bp.route('/api/my-profile')
def my_profile():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify({})
    contacts = enote.get_all_contacts()
    owner_contacts = [c for c in contacts if c.get('ОбъектВладелец') == user.enote_guid]
    if owner_contacts:
        c = owner_contacts[0]
        return jsonify({
            "full_name": f"{c.get('Фамилия', '')} {c.get('Имя', '')}".strip(),
            "phone": user.phone,
            "email": user.email
        })
    return jsonify({"phone": user.phone, "email": user.email})

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
        return redirect("/login")
    return render_template("settings.html")
