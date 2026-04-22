from flask import Blueprint, render_template, session, redirect, jsonify
from models import User

doctor_bp = Blueprint('doctor', __name__)

def is_verified_doctor():
    """Перевіряє, чи користувач є підтвердженим лікарем"""
    user_id = session.get("user_id")
    if not user_id:
        return False
    user = User.query.get(user_id)
    return user and user.is_doctor and user.is_verified

@doctor_bp.route('/doctor')
def doctor_panel():
    if "user_id" not in session:
        return redirect("/login")
    user = User.query.get(session["user_id"])
    if not user:
        session.clear()
        return redirect("/login")
    if not user.is_doctor or not user.is_verified:
        return redirect("/dashboard")
    return render_template("doctor.html")

# Захищений API-ендпоінт для лікарів
@doctor_bp.route('/api/doctor/patients', methods=['GET'])
def get_doctor_patients():
    """Отримати список пацієнтів лікаря (тільки для лікарів)"""
    if not is_verified_doctor():
        return jsonify({"error": "Доступ заборонено"}), 403
    
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    
    # TODO: отримати реальних пацієнтів з ENOTE
    return jsonify({
        "doctor_id": user.id,
        "doctor_phone": user.phone,
        "patients": []  # тут будуть пацієнти з ENOTE
    }), 200