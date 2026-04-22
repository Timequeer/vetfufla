from datetime import datetime
from flask import session, request
from models import db

class AuditLog(db.Model):
    """Таблиця для зберігання логів дій користувачів"""
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    user_phone = db.Column(db.String(20), nullable=True)
    action = db.Column(db.String(200), nullable=False)
    ip_address = db.Column(db.String(50), nullable=True)
    endpoint = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

def log_action(user_id, user_phone, action, endpoint=None):
    """Записує дію користувача в базу даних"""
    try:
        log = AuditLog(
            user_id=user_id,
            user_phone=user_phone,
            action=action,
            ip_address=request.remote_addr if request else None,
            endpoint=endpoint or request.endpoint if request else None
        )
        db.session.add(log)
        db.session.commit()
        print(f"[LOG] {user_phone}: {action}")
    except Exception as e:
        print(f"[LOG ERROR] {e}")

def log_user_action(action):
    """Спрощена функція для логування дії поточного користувача"""
    user_id = session.get("user_id")
    if user_id:
        from models import User
        user = User.query.get(user_id)
        if user:
            log_action(user.id, user.phone, action, request.endpoint)