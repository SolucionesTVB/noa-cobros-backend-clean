from datetime import datetime
from app import db

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, index=True, nullable=False)
    # Guardamos SIEMPRE hash de la contraseña aquí:
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), default="client", index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
