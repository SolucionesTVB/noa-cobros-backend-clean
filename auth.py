from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
import os

# importar db desde el módulo correcto (app / application / main)
try:
    from app import db
except Exception:
    try:
        from application import db
    except Exception:
        from main import db

from models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")

@bp.post("/bootstrap-admin")
def bootstrap_admin():
    key = request.headers.get("X-Bootstrap-Key")
    if not key or key != os.getenv("BOOTSTRAP_ADMIN_KEY"):
        return jsonify({"error":"unauthorized"}), 401
    if User.query.filter_by(role="admin").first():
        return jsonify({"error":"admin already exists"}), 409
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error":"username/password requeridos"}), 400
    u = User(username=username, role="admin")
    if hasattr(u,"password_hash"): u.password_hash = generate_password_hash(password)
    elif hasattr(u,"password"):    u.password      = generate_password_hash(password)
    else: return jsonify({"error":"modelo User sin campo password"}), 500
    db.session.add(u); db.session.commit()
    token = create_access_token(identity={"u": u.username, "r":"admin"}, expires_delta=timedelta(hours=12))
    return jsonify({"ok":True,"access_token":token})

@bp.post("/login")
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    u = User.query.filter_by(username=username).first()
    if not u: return jsonify({"error":"credenciales inválidas"}), 401
    pwd_hash = getattr(u,"password_hash","") or getattr(u,"password","")
    if not check_password_hash(pwd_hash, password):
        return jsonify({"error":"credenciales inválidas"}), 401
    token = create_access_token(identity={"u": u.username, "r": getattr(u,"role","client")}, expires_delta=timedelta(hours=12))
    return jsonify({"access_token": token})

@bp.post("/admin/create-user")
@jwt_required()
def admin_create_user():
    ident = get_jwt_identity() or {}
    if ident.get("r") not in ("admin","superadmin"):
        return jsonify({"error":"admin only"}), 403
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "client").strip().lower()
    parent_username = (data.get("parent_username") or "").strip().lower()
    if not username or not password:
        return jsonify({"error":"username/password requeridos"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error":"usuario ya existe"}), 409
    u = User(username=username, role=role if role in ("admin","tester","client") else "client")
    if hasattr(u,"password_hash"): u.password_hash = generate_password_hash(password)
    elif hasattr(u,"password"):    u.password      = generate_password_hash(password)
    else: return jsonify({"error":"modelo User sin campo password"}), 500
    if parent_username and hasattr(u,"parent_id"):
        parent = User.query.filter_by(username=parent_username).first()
        if parent and getattr(parent,"id",None):
            u.parent_id = parent.id
    db.session.add(u); db.session.commit()
    return jsonify({"ok":True})
