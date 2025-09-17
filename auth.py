from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
import os, inspect, importlib, pathlib, types

bp = Blueprint("auth", __name__, url_prefix="/auth")

# cache
_CACHE = {"ready": False, "db": None, "User": None, "fld_user": None, "fld_pwd": None, "fld_role": None}

_USERNAME_FIELDS = ("username","email","correo","user","login")
_PASSWORD_FIELDS = ("password_hash","password","hashed_password","pass_hash","clave","contrasena")
_ROLE_FIELDS     = ("role","rol","perfil")

def _resolve_db_user():
    if _CACHE["ready"]:
        return _CACHE["db"], _CACHE["User"], _CACHE["fld_user"], _CACHE["fld_pwd"], _CACHE["fld_role"]

    # 1) Permitir mapeo por variables de entorno (opcional, por si quieres forzarlo)
    mod_user = os.getenv("NOA_USER_MODULE")
    cls_user = os.getenv("NOA_USER_CLASS")
    mod_db   = os.getenv("NOA_DB_MODULE")  # p.ej. "app" o "models


# === UN SOLO COMANDO PARA DEJAR /auth LISTO EN EL CLEAN ===
set -e; set +H
cd ~/noa-cobros-backend-clean

# 0) Detectar rama de deploy (fallback a main)
BR=$(git remote show origin 2>/dev/null | sed -n '/HEAD branch/s/.*: //p'); [ -z "$BR" ] && BR=main
echo "Rama de deploy: $BR"

# 1) Backups por si acaso
cp -n app.py app.bak.py 2>/dev/null || true
cp -n auth.py auth.bak.py 2>/dev/null || true

# 2) auth.py ROBUSTO (autodetección de db + modelo usuario + endpoint /auth/_debug)
cat > auth.py <<'PY'
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
import os, sys, inspect, importlib, pathlib
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec

bp = Blueprint("auth", __name__, url_prefix="/auth")
_CACHE = {"db": None, "User": None, "scan": [], "ready": False}

def _load(path: str, name: str):
    try:
        loader = SourceFileLoader(name, path)
        spec = spec_from_loader(name, loader)
        mod = module_from_spec(spec)
        loader.exec_module(mod)
        return mod
    except Exception:
        return None

def _resolve_db_user():
    if _CACHE["ready"]:
        return _CACHE["db"], _CACHE["User"]

    root = pathlib.Path(__file__).parent.resolve()
    sys.path.insert(0, str(root))
    cand_mods, seen_paths = [], set()

    # Intentar módulos típicos
    for modname in ("app","application","main","models"):
        try:
            m = importlib.import_module(modname)
            if getattr(m,"__file__",None):
                cand_mods.append(m); _CACHE["scan"].append(f"import {modname} OK")
        except Exception as e:
            _CACHE["scan"].append(f"import {modname} FAIL: {e}")

    # Escanear archivos .py (hasta 2 niveles)
    for p in list(root.glob("*.py")) + list(root.glob("*/*.py")):
        sp = str(p)
        if any(bad in sp for bad in ("/.venv/","/venv/","/site-packages/","/__pycache__/")):
            continue
        if sp in seen_paths: continue
        seen_paths.add(sp)
        m = _load(sp, f"_mod_{len(seen_paths)}")
        if m: 
            cand_mods.append(m); _CACHE["scan"].append(f"load {p.name} OK")

    db = None; User = None

    # Heurística: db con .session y/o .Model (Flask-SQLAlchemy)
    for M in cand_mods:
        cand_db = getattr(M, "db", None)
        if cand_db and hasattr(cand_db, "session"):
            db = db or cand_db
        # User class: tiene __table__/__tablename__/__mapper__ + username + password(_hash)
        for _, cls in inspect.getmembers(M, inspect.isclass):
            fields = set(dir(cls))
            if not (("__table__" in fields or "__tablename__" in fields or "__mapper__" in fields) and "username" in fields):
                continue
            if not ("password_hash" in fields or "password" in fields):
                continue
            # evitar agarrar clases de otras libs
            if cls.__module__.startswith("sqlalchemy."): 
                continue
            User = User or cls
        if db and User: break

    _CACHE.update({"db": db, "User": User, "ready": True})
    return db, User

@bp.get("/_debug")
def debug():
    db, User = _resolve_db_user()
    return jsonify({
        "db_found": bool(db),
        "user_found": bool(User),
        "user_class": getattr(User, "__name__", None),
        "user_module": getattr(User, "__module__", None),
        "scan": _CACHE["scan"][:40]
    })

def _set_pwd(u, raw):
    if hasattr(u,"password_hash"): u.password_hash = generate_password_hash(raw)
    elif hasattr(u,"password"):    u.password      = generate_password_hash(raw)

def _set_role(u, role):
    if hasattr(u,"role"): u.role = role

@bp.post("/bootstrap-admin")
def bootstrap_admin():
    key = request.headers.get("X-Bootstrap-Key")
    if not key or key != os.getenv("BOOTSTRAP_ADMIN_KEY"):
        return jsonify({"error":"unauthorized"}), 401

    db, User = _resolve_db_user()
    if not db or not User:
        return jsonify({"error":"server misconfigured (User/db not found)"}), 500

    q = db.session.query(User)
    already = q.filter(getattr(User,"role","")=="admin").first() if hasattr(User,"role") else None
    if already:
        return jsonify({"error":"admin already exists"}), 409

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error":"username/password requeridos"}), 400

    u = User(); 
    if hasattr(u,"username"): u.username = username
    _set_pwd(u, password); _set_role(u, "admin")
    db.session.add(u); db.session.commit()

    tok = create_access_token(identity={"u": getattr(u,"username",username), "r": getattr(u,"role","admin")},
                              expires_delta=timedelta(hours=12))
    return jsonify({"ok":True, "access_token": tok})

@bp.post("/login")
def login():
    db, User = _resolve_db_user()
    if not db or not User:
        return jsonify({"error":"server misconfigured (User/db not found)"}), 500

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    pwd = data.get("password") or ""
    u = db.session.query(User).filter(getattr(User,"username")==username).first()
    if not u: return jsonify({"error":"credenciales inválidas"}), 401
    ph = getattr(u,"password_hash","") or getattr(u,"password","")
    if not check_password_hash(ph, pwd): return jsonify({"error":"credenciales inválidas"}), 401

    tok = create_access_token(identity={"u": getattr(u,"username",username), "r": getattr(u,"role","client")},
                              expires_delta=timedelta(hours=12))
    return jsonify({"access_token": tok})

@bp.post("/admin/create-user")
@jwt_required()
def admin_create_user():
    db, User = _resolve_db_user()
    if not db or not User:
        return jsonify({"error":"server misconfigured (User/db not found)"}), 500

    ident = get_jwt_identity() or {}
    me = db.session.query(User).filter(getattr(User,"username")==ident.get("u","")).first()
    if not me or not (getattr(me,"role",None) in ("admin","superadmin")):
        return jsonify({"error":"admin only"}), 403

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    pwd = data.get("password") or ""
    role = (data.get("role") or "client").strip().lower()

    if not username or not pwd:
        return jsonify({"error":"username/password requeridos"}), 400
    if db.session.query(User).filter(getattr(User,"username")==username).first():
        return jsonify({"error":"usuario ya existe"}), 409

    u = User()
    if hasattr(u,"username"): u.username = username
    _set_pwd(u, pwd); _set_role(u, role if role in ("admin","tester","client") else "client")
    db.session.add(u); db.session.commit()
    return jsonify({"ok":True})
