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

def get_appointments_by_owner(self, owner_guid):
    pets = self.get_pets_by_owner(owner_guid)
    all_appointments = []
    for pet in pets:
        pet_key = pet.get('Ref_Key')
        if not pet_key:
            continue
        url = self._build_url("Task_ПредварительнаяЗапись")
        params = {
            "$filter": f"Карточка_Key eq guid'{pet_key}'",
            "$orderby": "ЗаписьНаДату desc",
            "$top": 20,
            "$format": "json"
        }
        try:
            r = self.session.get(url, params=params, timeout=25)
            if r.ok:
                data = r.json().get('value', [])
                for a in data:
                    a['_pet_name'] = pet.get('Description', '')
                    all_appointments.append(a)
        except Exception:
            pass
    all_appointments.sort(key=lambda x: x.get('ЗаписьНаДату', ''), reverse=True)
    self._cache[f"appointments:{owner_guid}"] = (time.time(), all_appointments)
    return all_appointments
    
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

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
