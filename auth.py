from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
import os, sys, inspect, importlib, pathlib, types
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec

bp = Blueprint("auth", __name__, url_prefix="/auth")

# --- cache global para no re-escanear en cada request ---
_RES_CACHE = {"db": None, "User": None, "ready": False}

def _load_module_from_path(path: str, name: str) -> types.ModuleType | None:
    try:
        loader = SourceFileLoader(name, path)
        spec = spec_from_loader(name, loader)
        mod = module_from_spec(spec)
        loader.exec_module(mod)
        return mod
    except Exception:
        return None

def _resolve_db_user():
    """Detecta dinámicamente el objeto db (Flask-SQLAlchemy) y la clase de usuario (tiene username + password[_hash])."""
    if _RES_CACHE.get("ready"):
        return _RES_CACHE["db"], _RES_CACHE["User"]

    root = pathlib.Path(__file__).parent.resolve()
    project_root = str(root)

    candidates = []
    imported = set()

    # 1) intentar módulos conocidos
    for modname in ("app", "application", "main", "models"):
        try:
            M = importlib.import_module(modname)
            if getattr(M, "__file__", "") and str(getattr(M, "__file__")).startswith(project_root):
                candidates.append(M); imported.add(M.__name__)
        except Exception:
            pass

    # 2) escanear .py en el proyecto (profundidad 2) y cargarlos con loader
    to_scan = []
    for p in root.glob("*.py"):
        to_scan.append(p)
    for p in root.glob("*/*.py"):
        to_scan.append(p)

    idx = 0
    for p in to_scan:
        # omitir virtualenvs/archivos de build
        if any(seg in str(p) for seg in ("/.venv/", "/venv/", "/site-packages/", "/__pycache__/")):
            continue
        name = f"_mod_{idx}"
        idx += 1
        m = _load_module_from_path(str(p), name)
        if m and getattr(m, "__file__", "").startswith(project_root):
            candidates.append(m)

    db = None
    User = None

    # 3) buscar db y modelo usuario
    for M in candidates:
        # db: objeto con 'session' y, comúnmente, clase Model
        cand_db = getattr(M, "db", None)
        if cand_db and hasattr(cand_db, "session"):
            db = db or cand_db

        # modelo usuario: clase con __table__/__tablename__ y atributos username + (password o password_hash)
        for _, cls in inspect.getmembers(M, inspect.isclass):
            fields = set(dir(cls))
            has_table = ("__table__" in fields) or ("__tablename__" in fields)
            has_user = "username" in fields
            has_pwd  = ("password_hash" in fields) or ("password" in fields)
            if has_table and has_user and has_pwd:
                User = User or cls

        if db and User:
            break

    _RES_CACHE["db"] = db
    _RES_CACHE["User"] = User
    _RES_CACHE["ready"] = True
    return db, User

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

    # ¿Existe ya algún admin?
    q = db.session.query(User)
    exists_admin = None
    if hasattr(User, "role"):
        exists_admin = q.filter(getattr(User,"role")=="admin").first()
    else:
        exists_admin = q.first()  # si no hay role, asumimos que el primero ya existe

    if exists_admin and getattr(exists_admin,"role",None) == "admin":
        return jsonify({"error":"admin already exists"}), 409

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error":"username/password requeridos"}), 400

    u = User()
    if hasattr(u,"username"): u.username = username
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

    u = db.session.query(User).filter(getattr(User,"username")==username).first()
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
