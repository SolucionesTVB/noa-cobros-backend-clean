from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
import importlib, inspect, os

bp = Blueprint("auth", __name__, url_prefix="/auth")

def _resolve_db_user():
    """Encuentra db y el modelo de usuario, sin importar cómo se llame o dónde esté."""
    db = None
    User = None
    # módulos donde normalmente viven db y los modelos
    for modname in ("app", "application", "main", "models"):
        try:
            M = importlib.import_module(modname)
        except Exception:
            continue
        if not db:
            db = getattr(M, "db", None)
        # buscar clases con tabla y campos de usuario
        for _, cls in inspect.getmembers(M, inspect.isclass):
            has_table = hasattr(cls, "__table__") or hasattr(cls, "__tablename__")
            if not has_table: 
                continue
            if not hasattr(cls, "username"): 
                continue
            if not (hasattr(cls, "password_hash") or hasattr(cls, "password")):
                continue
            User = cls
            break
        if db and User:
            return db, User
    return None, None

def _set_password(u, raw):
    if hasattr(u, "password_hash"):
        u.password_hash = generate_password_hash(raw)
    elif hasattr(u, "password"):
        u.password = generate_password_hash(raw)

def _set_role(u, role):
    if hasattr(u, "role"):
        u.role = role

def _link_parent(u, parent):
    pid = getattr(parent, "id", None)
    if pid is None:
        return
    for f in ("parent_id", "owner_id", "account_id", "company_id", "creator_id"):
        if hasattr(u, f):
            setattr(u, f, pid)
            break

@bp.post("/bootstrap-admin")
def bootstrap_admin():
    key = request.headers.get("X-Bootstrap-Key")
    if not key or key != os.getenv("BOOTSTRAP_ADMIN_KEY"):
        return jsonify({"error":"unauthorized"}), 401

    db, User = _resolve_db_user()
    if not db or not User:
        return jsonify({"error":"server misconfigured (User/db not found)"}), 500

    # ¿ya existe admin?
    exists_admin = db.session.query(User).filter(getattr(User, "role", None) == "admin").first() if hasattr(User,"role") else db.session.query(User).first()
    if exists_admin and hasattr(exists_admin, "role") and exists_admin.role == "admin":
        return jsonify({"error":"admin already exists"}), 409

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error":"username/password requeridos"}), 400

    # si NO hay admin, creamos uno
    u = User()
    if hasattr(u, "username"): u.username = username
    _set_password(u, password)
    _set_role(u, "admin")
    db.session.add(u); db.session.commit()

    token = create_access_token(identity={"u": getattr(u,"username",username), "r": getattr(u,"role","admin")},
                                expires_delta=timedelta(hours=12))
    return jsonify({"ok":True, "access_token": token})

@bp.post("/login")
def login():
    db, User = _resolve_db_user()
    if not db or not User:
        return jsonify({"error":"server misconfigured (User/db not found)"}), 500

    data = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    q = db.session.query(User).filter(getattr(User,"username")==username)
    u = q.first()
    if not u:
        return jsonify({"error":"credenciales inválidas"}), 401

    pwd_hash = getattr(u, "password_hash", "") or getattr(u, "password", "")
    if not check_password_hash(pwd_hash, password):
        return jsonify({"error":"credenciales inválidas"}), 401

    token = create_access_token(identity={"u": getattr(u,"username",username), "r": getattr(u,"role","client")},
                                expires_delta=timedelta(hours=12))
    return jsonify({"access_token": token})

@bp.post("/admin/create-user")
@jwt_required()
def admin_create_user():
    db, User = _resolve_db_user()
    if not db or not User:
        return jsonify({"error":"server misconfigured (User/db not found)"}), 500

    ident = get_jwt_identity() or {}
    admin_user = db.session.query(User).filter(getattr(User,"username")==ident.get("u","")).first()
    if not admin_user or not (getattr(admin_user,"role",None) in ("admin","superadmin")):
        return jsonify({"error":"admin only"}), 403

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    role     = (data.get("role") or "client").strip().lower()
    parent_username = (data.get("parent_username") or "").strip().lower()

    if not username or not password:
        return jsonify({"error":"username/password requeridos"}), 400

    if db.session.query(User).filter(getattr(User,"username")==username).first():
        return jsonify({"error":"usuario ya existe"}), 409

    u = User()
    if hasattr(u,"username"): u.username = username
    _set_password(u, password)
    _set_role(u, role if role in ("admin","tester","client") else "client")

    if parent_username:
        parent = db.session.query(User).filter(getattr(User,"username")==parent_username).first()
        if parent:
            _link_parent(u, parent)

    db.session.add(u); db.session.commit()
    return jsonify({"ok":True})
