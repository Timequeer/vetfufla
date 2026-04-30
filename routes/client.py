from flask import Blueprint, render_template, session, redirect, jsonify
from models import User

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
    from services.enote_service import enote
    # Получаем всех животных (без фильтра)
    all_pets = enote.get_pets()
    if not all_pets:
        return jsonify([])
    # Фильтруем по GUID клиента на стороне Python
    my_pets = [pet for pet in all_pets if pet.get('Хозяин_Key') == user.enote_guid]
    return jsonify(my_pets)

@client_bp.route('/api/debug-enote')
def debug_enote():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify({"error": "Немає enote_guid"}), 400
    from services.enote_service import enote
    url = enote._build_url("Catalog_Карточки")
    params = {"$format": "json", "$filter": f"Хозяин_Key eq guid'{user.enote_guid}'"}
    r = enote.session.get(url, params=params)
    return jsonify({
        "status_code": r.status_code,
        "ok": r.ok,
        "text": r.text[:500]  # перші 500 символів відповіді
    })

@client_bp.route('/api/my-analyses')
def my_analyses():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Не авторизовано"}), 401
    user = User.query.get(user_id)
    if not user or not user.enote_guid:
        return jsonify([])
    from services.enote_service import enote
    pets = enote.get_pets(client_guid=user.enote_guid)
    if not pets:
        return jsonify([])
    all_analyses = []
    for pet in pets:
        analyses = enote.get_analyses(pet_guid=pet['Ref_Key'])
        if analyses:
            all_analyses.extend(analyses)
    return jsonify(all_analyses)

@client_bp.route('/settings')
def settings():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("settings.html")
