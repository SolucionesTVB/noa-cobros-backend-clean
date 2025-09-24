# simple_auth.py — Login sencillo + verificación de token para NOA
import os, time
from flask import Blueprint, request, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import check_password_hash

# Importa tu DB y el modelo User
from models import db, User

bp = Blueprint("auth", __name__, url_prefix="/auth")

def _serializer():
    secret = os.getenv("JWT_SECRET_KEY", "change-me")
    return URLSafeTimedSerializer(secret_key=secret, salt="noa-auth")

def create_access_token(user_id: str | int, expires_sec: int = 60*60*8):
    s = _serializer()
    payload = {"sub": str(user_id), "iat": int(time.time())}
    # firmamos (expiración la valida quien verifica con max_age)
    return s.dumps(payload)

def decode_access(token: str):
    s = _serializer()
    data = s.loads(token, max_age=60*60*24)  # válido 24h
    # devolvemos en formato que NOA.init usa: {"sub": "..."}
    return {"sub": data.get("sub")}

def _password_ok(user: User, raw: str) -> bool:
    # soporta User.password_hash (hash) o User.password (en claro)
    if hasattr(user, "password_hash") and user.password_hash:
        try:
            return check_password_hash(user.password_hash, raw)
        except Exception:
            pass
    if hasattr(user, "password") and user.password:
        # si guardaste la contraseña en claro (no recomendado), comparamos directo
        return user.password == raw
    return False

@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username") or data.get("user") or data.get("login")
    password = data.get("password") or data.get("pass") or data.get("pwd")
    if not username or not password:
        return jsonify({"error": "username/password requeridos"}), 400

    u = User.query.filter_by(username=username).first()
    if not u or not _password_ok(u, password):
        return jsonify({"error": "credenciales inválidas"}), 401

    token = create_access_token(u.id)
    return jsonify({"access_token": token, "token_type": "bearer", "user": {"id": u.id, "username": u.username}})

def register_auth(app):
    app.register_blueprint(bp)
