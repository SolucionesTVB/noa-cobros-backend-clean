from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
from app import db
import os

bp = Blueprint("auth", __name__, url_prefix="/auth")

# ------------ utilidades de autodetección ------------
# nombres posibles de campos
USER_FIELD_CANDIDATES = ["username", "user", "usuario", "login"]
PASS_FIELD_CANDIDATES = ["password_hash", "password", "passhash", "pass", "pwd", "clave", "contrasena", "contraseña"]
ROLE_FIELD_CANDIDATES = ["role", "rol", "perfil"]

def _load_models():
    try:
        import models  # noqa: F401
    except Exception:
        # si models tiene errores, igual seguimos y probamos con lo registrado en SQLAlchemy
        pass

def _iter_model_classes():
    # clases registradas por SQLAlchemy
    seen = set()
    if hasattr(db.Model, "_decl_class_registry"):
        for k, v in db.Model._decl_class_registry.items():
            if isinstance(v, type) and issubclass(v, db.Model):
                if v not in seen:
                    seen.add(v); yield v
    # subclasses también
    for cls in list(db.Model.__subclasses__()):
        if cls not in seen:
            seen.add(cls); yield cls

def _attrs(obj):
    try:
        return set(dir(obj))
    except Exception:
        return set()

def _pick_attr(obj, candidates):
    a = _attrs(obj)
    for name in candidates:
        if name in a:
            return name
    return None

def _get_user_model_and_fields():
    _load_models()

    best = None
    best_score = -1
    best_fields = {}

    for cls in _iter_model_classes():
        attrs = _attrs(cls)
        u = _pick_attr(cls, USER_FIELD_CANDIDATES)
        p = _pick_attr(cls, PASS_FIELD_CANDIDATES)
        r = _pick_attr(cls, ROLE_FIELD_CANDIDATES)
        score = (2 if u else 0) + (2 if p else 0) + (1 if r else 0)
        if score > best_score and (u and p):
            best = cls
            best_score = score
            best_fields = {"user": u, "pass": p, "role": r}

    if not best:
        return None, None

    return best, best_fields

def _hash_password(raw: str):
    return generate_password_hash(raw)

def _check_password(hashed_or_raw, raw):
    # si el campo guardado ya está hasheado, check_password_hash funciona
    try:
        return check_password_hash(hashed_or_raw, raw)
    except Exception:
        # si no está hasheado, comparamos directo (no recomendado, pero evita 500 en entornos de prueba)
        return hashed_or_raw == raw

# ---------------- diagnóstico ----------------
@bp.get("/_diagnose")
def _diagnose():
    _load_models()
    out = []
    for cls in _iter_model_classes():
        out.append({
            "class": cls.__name__,
            "attrs": sorted([a for a in _attrs(cls) if not a.startswith("_")])[:80]
        })
    return jsonify({"models": out})

# ---------------- rutas ----------------
@bp.post("/bootstrap-admin")
def bootstrap_admin():
    key = request.headers.get("X-Bootstrap-Key")
    if not key or key != os.getenv("BOOTSTRAP_ADMIN_KEY"):
        return jsonify({"error": "unauthorized"}), 401

    User, f = _get_user_model_and_fields()
    if not User:
        return jsonify({
            "error": "user_model_not_found",
            "hint": "No encontré una clase db.Model con campos tipo username + password.",
            "try": "/auth/_diagnose para ver clases y atributos"
        }), 400

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "username/password requeridos"}), 400

    # ¿ya existe admin?
    q = db.session.query(User)
    if f.get("role"):
        exists = q.filter(getattr(User, f["role"]) == "admin").first()
        if exists:
            return jsonify({"error": "admin already exists"}), 409

    # crear admin
    u = User()
    setattr(u, f["user"], username)
    # escribir hash siempre (aunque el campo se llame "password")
    setattr(u, f["pass"], _hash_password(password))
    if f.get("role"):
        setattr(u, f["role"], "admin")

    db.session.add(u)
    db.session.commit()

    tok = create_access_token(
        identity={"u": username, "r": "admin"},
        expires_delta=timedelta(hours=12),
    )
    return jsonify({"ok": True, "access_token": tok})

@bp.post("/login")
def login():
    User, f = _get_user_model_and_fields()
    if not User:
        return jsonify({"error": "user_model_not_found", "try": "/auth/_diagnose"}), 400

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    pwd = data.get("password") or ""
    if not username or not pwd:
        return jsonify({"error": "username/password requeridos"}), 400

    u = db.session.query(User).filter(getattr(User, f["user"]) == username).first()
    if not u:
        return jsonify({"error": "credenciales inválidas"}), 401

    stored = getattr(u, f["pass"])
    if not _check_password(stored, pwd):
        return jsonify({"error": "credenciales inválidas"}), 401

    role = getattr(u, f["role"]) if f.get("role") else "client"
    tok = create_access_token(
        identity={"u": username, "r": role},
        expires_delta=timedelta(hours=12),
    )
    return jsonify({"access_token": tok})

@bp.post("/admin/create-user")
@jwt_required()
def admin_create_user():
    User, f = _get_user_model_and_fields()
    if not User:
        return jsonify({"error": "user_model_not_found", "try": "/auth/_diagnose"}), 400

    ident = get_jwt_identity() or {}
    me = db.session.query(User).filter(getattr(User, f["user"]) == ident.get("u", "")).first()
    me_role = getattr(me, f["role"], None) if me and f.get("role") else None
    if not me or me_role not in ("admin", "superadmin"):
        return jsonify({"error": "admin only"}), 403

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    pwd = data.get("password") or ""
    role = (data.get("role") or "client").strip().lower()
    parent_username = (data.get("parent_username") or "").strip().lower()

    if not username or not pwd:
        return jsonify({"error": "username/password requeridos"}), 400

    if db.session.query(User).filter(getattr(User, f["user"]) == username).first():
        return jsonify({"error": "usuario ya existe"}), 409

    u = User()
    setattr(u, f["user"], username)
    setattr(u, f["pass"], _hash_password(pwd))
    if f.get("role"):
        setattr(u, f["role"], role if role in ("admin", "tester", "client") else "client")

    if parent_username:
        p = db.session.query(User).filter(getattr(User, f["user"]) == parent_username).first()
        if p:
            pid = getattr(p, "id", None)
            for rel in ("parent_id", "owner_id", "account_id", "company_id", "creator_id"):
                if hasattr(u, rel) and pid is not None:
                    setattr(u, rel, pid)
                    break

    db.session.add(u)
    db.session.commit()
    return jsonify({"ok": True})
