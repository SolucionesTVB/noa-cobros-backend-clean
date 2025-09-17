from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, 
get_jwt_identity
from datetime import timedelta
# OJO: estos imports asumen nombres comunes; si luego falla, cambiamos 
aquí.
from app import db
from models import User
import os

bp = Blueprint("auth", __name__, url_prefix="/auth")

@bp.post("/bootstrap-admin")
def bootstrap_admin():
    key = request.headers.get("X-Bootstrap-Key")
    if not key or key != os.getenv("BOOTSTRAP_ADMIN_KEY"):
        return jsonify({"error":"unauthorized"}), 401

    q = db.session.query(User)
    exists = q.filter(getattr(User,"role","")=="admin").first() if 
hasattr(User,"role") else None
    if exists:
        return jsonify({"error":"admin already exists"}), 409

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error":"username/password requeridos"}), 400

    u = User()
    if hasattr(u,"username"): u.username = username
    if hasattr(u,"password_hash"): u.password_hash = 
generate_password_hash(password)
    elif hasattr(u,"password"):    u.password      = 
generate_password_hash(password)
    if hasattr(u,"role"): u.role = "admin"
    db.session.add(u); db.session.commit()

    tok = create_access_token(identity={"u": 
getattr(u,"username",username), "r": getattr(u,"role","admin")},
                              expires_delta=timedelta(hours=12))
    return jsonify({"ok": True, "access_token": tok})

@bp.post("/login")
def login():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    pwd = data.get("password") or ""

    u = 
db.session.query(User).filter(getattr(User,"username")==username).first()
    if not u: return jsonify({"error":"credenciales inválidas"}), 401

    ph = getattr(u,"password_hash","") or getattr(u,"password","")
    if not check_password_hash(ph, pwd): return 
jsonify({"error":"credenciales inválidas"}), 401

    tok = create_access_token(identity={"u": 
getattr(u,"username",username), "r": getattr(u,"role","client")},
                              expires_delta=timedelta(hours=12))
    return jsonify({"access_token": tok})

@bp.post("/admin/create-user")
@jwt_required()
def admin_create_user():
    ident = get_jwt_identity() or {}
    me = 
db.session.query(User).filter(getattr(User,"username")==ident.get("u","")).first()
    if not me or not (getattr(me,"role",None) in ("admin","superadmin")):
        return jsonify({"error":"admin only"}), 403

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    pwd = data.get("password") or ""
    role = (data.get("role") or "client").strip().lower()
    parent_username = (data.get("parent_username") or "").strip().lower()

    if not username or not pwd:
        return jsonify({"error":"username/password requeridos"}), 400
    if 
db.session.query(User).filter(getattr(User,"username")==username).first():
        return jsonify({"error":"usuario ya existe"}), 409

    u = User()
    if hasattr(u,"username"): u.username = username
    if hasattr(u,"password_hash"): u.password_hash = 
generate_password_hash(pwd)
    elif hasattr(u,"password"):    u.password      = 
generate_password_hash(pwd)
    if hasattr(u,"role"): u.role = role if role in 
("admin","tester","client") else "client"

    if parent_username:
        p = 
db.session.query(User).filter(getattr(User,"username")==parent_username).first()
        if p:
            pid = getattr(p,"id",None)
            for f in 
("parent_id","owner_id","account_id","company_id","creator_id"):
                if hasattr(u,f) and pid is not None:
                    setattr(u,f,pid); break

    db.session.add(u); db.session.commit()
    return jsonify({"ok": True})

