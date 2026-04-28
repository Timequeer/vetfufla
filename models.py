from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    enote_guid = db.Column(db.String(36), nullable=True)
    is_doctor = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)   # Нова колонка
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    notifications = db.relationship("NotificationSetting", backref="user", lazy=True)
    pets = db.relationship("UserPet", backref="owner", lazy=True)

    def __repr__(self):
        return f"<User {self.phone}>"

class UserPet(db.Model):
    __tablename__ = "user_pets"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    pet_guid = db.Column(db.String(36), nullable=False)
    pet_name = db.Column(db.String(100))
    species = db.Column(db.String(50))

class NotificationSetting(db.Model):
    __tablename__ = "notification_settings"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    channel = db.Column(db.String(20), nullable=False)
    contact = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class AuthCode(db.Model):
    __tablename__ = "auth_codes"
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False)      # номер телефону користувача
    code = db.Column(db.String(6), nullable=False)
    chat_id = db.Column(db.String(20), nullable=True)     # Telegram chat_id для прив'язки
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    attempts = db.Column(db.Integer, default=0) 