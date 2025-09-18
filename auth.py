from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
from app import db
import os

bp = Blueprint("auth", __name__, url_prefix="/auth")

# ---- Utilidad: detectar la clase de usuario sin importar el nombre ----
def _get_user_model():
    """
    Busca en todos los modelos (subclases de db.Model) uno que tenga:
      - username
      - y (password_hash o password)
    Opcional: role
    """
    # Importa todos los modelos para que las clases estén registradas
    try:
        import models  # noqa: F401
    except Exception:
        pass

    # Algunas apps registran modelos en _decl_class_registry (SQLAlchemy clásico)
    registries = []
    if hasattr(db.Model, "_decl_class_registry"):
        registries.append(getattr(db.Model, "_decl_class_registry"))

    # Y otras vía __subclasses__()
    subclasses = list(db.Model.__subclasses__())

    # Construir lista única de clases candidatas
    candidates = set()
    for reg in registries:
        for k, v in reg.items():
            if isinstance(v, type) and issubclass(v, db.Model):
                candidates.add(v)
    for cls in subclasses:
        candidates.add(cls)

    best = None
    best_score = -1
    for cls in candidates:
        attrs = dir(cls)
        has_user = any(a == "username" for a in attrs)
        has_pass = any(a in ("password_hash", "password") for a in attrs)
        score = 0
        if has_user: score += 2
        if has_pass: score += 2
        if any(a == "role" for a in attrs): score += 1
        if score > best_score and (has_user and has_pass):
            best, best_score = cls, score

    if not best:
        raise RuntimeError(
            "No se encontró un modelo de usuario: necesito una clase db.Model con "
            "atributos 'username' y 'password_hash' (o 'password')."
        )
    return best

def _password_get(u):
    return getattr(u, "password_hash", None) or getattr(u, "password", None)

# ----------------------- RUTAS -----------------------

@bp.get("/_diagnose")
def _diagnose():
    """Lista subclases de db.Model con sus atributos principales (solo lectura)."""
    from app import db
    try:
        import models  # asegura que se importen las clases
    except Exception as e:
        return jsonify({"error":"import models failed", "detail": str(e)}), 500

    out = []
    # clases registradas por SQLAlchemy (compat)
    regs = []
    if hasattr(db.Model, "_decl_class_registry"):
        regs.append(getattr(db.Model, "_decl_class_registry"))
    subs = list(db.Model.__subclasses__())

    seen = set()
    def attrs_of(cls):
        try:
            return sorted([a for a in dir(cls) if not a.startswith("_")][:50])
        except Exception:
            return []

    for reg in regs:
        for k,v in reg.items():
            if isinstance(v, type) and issubclass(v, db.Model) and v not in seen:
                seen.add(v); out.append({"class": v.__name__, "attrs": attrs_of(v)})
    for cls in subs:
        if cls not in seen:
            seen.add(cls); out.append({"class": cls.__name__, "attrs": attrs_of(cls)})
    return jsonify({"models": out})


@bp.post("/bootstrap-admin")
def bootstrap_admin():
    key = request.headers.get("X-Bootstrap-Key")
    if not key or key != os.getenv("BOOTSTRAP_ADMIN_KEY"):
        return jsonify({"error": "unauthorized"}), 401

    User = _get_user_model()

    # ¿ya hay admin?
    q = db.session.query(User)
    exists = None
    if hasattr(User, "role"):
        exists = q.filter(getattr(User, "role") == "admin").first()
    else:
        exists = None

    if exists:
        return jsonify({"error": "admin already exists"}), 409

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "username/password requeridos"}), 400

    u = User()
    if hasattr(u, "username"): u.username = username
    if hasattr(u, "password_hash"):
        u.password_hash = generate_password_hash(password)
    elif hasattr(u, "password"):
        u.password = generate_password_hash(password)
    if hasattr(u, "role"): u.role = "admin"

    db.session.add(u)
    db.session.commit()

    tok = create_access_token(
        identity={"u": getattr(u, "username", username), "r": getattr(u, "role", "admin")},
        expires_delta=timedelta(hours=12),
    )
    return jsonify({"ok": True, "access_token": tok})

@bp.post("/login")
def login():
    User = _get_user_model()
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    pwd = data.get("password") or ""

    u = db.session.query(User).filter(getattr(User, "username") == username).first()
    if not u:
        return jsonify({"error": "credenciales inválidas"}), 401

    ph = _password_get(u)
    if not ph or not check_password_hash(ph, pwd):
        return jsonify({"error": "credenciales inválidas"}), 401

    tok = create_access_token(
        identity={"u": getattr(u, "username", username), "r": getattr(u, "role", "client")},
        expires_delta=timedelta(hours=12),
    )
    return jsonify({"access_token": tok})

@bp.post("/admin/create-user")
@jwt_required()
def admin_create_user():
    User = _get_user_model()
    ident = get_jwt_identity() or {}
    me = db.session.query(User).filter(getattr(User, "username") == ident.get("u", "")).first()
    if not me or not (getattr(me, "role", None) in ("admin", "superadmin")):
        return jsonify({"error": "admin only"}), 403

    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    pwd = data.get("password") or ""
    role = (data.get("role") or "client").strip().lower()
    parent_username = (data.get("parent_username") or "").strip().lower()

    if not username or not pwd:
        return jsonify({"error": "username/password requeridos"}), 400
    if db.session.query(User).filter(getattr(User, "username") == username).first():
        return jsonify({"error": "usuario ya existe"}), 409

    u = User()
    if hasattr(u, "username"): u.username = username
    if hasattr(u, "password_hash"):
        u.password_hash = generate_password_hash(pwd)
    elif hasattr(u, "password"):
        u.password = generate_password_hash(pwd)
    if hasattr(u, "role"):
        u.role = role if role in ("admin", "tester", "client") else "client"

    if parent_username:
        p = db.session.query(User).filter(getattr(User, "username") == parent_username).first()
        if p:
            pid = getattr(p, "id", None)
            for f in ("parent_id", "owner_id", "account_id", "company_id", "creator_id"):
                if hasattr(u, f) and pid is not None:
                    setattr(u, f, pid)
                    break

    db.session.add(u)
    db.session.commit()
    return jsonify({"ok": True})
