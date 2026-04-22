from flask import Blueprint, render_template, session, jsonify, request
from models import User, db
from services.logger_service import AuditLog, log_action
from config import Config

admin_bp = Blueprint('admin', __name__)

def is_admin():
    """Перевіряє, чи користувач є адміністратором"""
    user_id = session.get("user_id")
    if not user_id:
        return False
    user = User.query.get(user_id)
    # Адміністратор - це користувач з телефоном зі списку ADMIN_PHONES
    return user and user.phone in getattr(Config, 'ADMIN_PHONES', [])

@admin_bp.route('/admin')
def admin_panel():
    """Адмін-панель - тільки для адміністраторів"""
    if not is_admin():
        return redirect("/dashboard")
    return render_template("admin.html")

@admin_bp.route('/api/admin/logs', methods=['GET'])
def get_logs():
    """Отримати логи (тільки для адміністраторів)"""
    if not is_admin():
        return jsonify({"error": "Доступ заборонено"}), 403
    
    limit = request.args.get('limit', 100, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    
    return jsonify([{
        "id": log.id,
        "user_phone": log.user_phone,
        "action": log.action,
        "ip_address": log.ip_address,
        "timestamp": log.timestamp.isoformat()
    } for log in logs])

@admin_bp.route('/api/admin/users', methods=['GET'])
def get_users():
    """Отримати список користувачів (тільки для адміністраторів)"""
    if not is_admin():
        return jsonify({"error": "Доступ заборонено"}), 403
    
    users = User.query.all()
    return jsonify([{
        "id": u.id,
        "phone": u.phone,
        "is_doctor": u.is_doctor,
        "is_verified": u.is_verified,
        "created_at": u.created_at.isoformat() if u.created_at else None
    } for u in users])