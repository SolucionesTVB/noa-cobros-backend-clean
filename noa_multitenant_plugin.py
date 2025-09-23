# noa_multitenant_plugin.py
# Plugin TODO EN UNO: seed de usuarios (tony/jeff/hermann) + rutas /orgs
# Requiere que tu proyecto tenga: models.py con db y User, y auth.py con /auth/login
import os
import uuid
from flask import request, jsonify

# importa tu DB y User desde models.py
from models import db, User

# --------- MODELOS TENANT (si ya existen, estos nombres deben coincidir) ---------
from sqlalchemy.sql import func

class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(80), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

class OrgMembership(db.Model):
    __tablename__ = "org_memberships"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # ⚠️ si tu users.id NO es Integer, cambia a db.String(36) o lo que uses
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id  = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role    = db.Column(db.String(20), nullable=False)  # owner/manager/agent/viewer/suspended
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

# --------------------- HELPERS SIMPLES ---------------------
def _hash_password(raw: str):
    try:
        from werkzeug.security import generate_password_hash
        return generate_password_hash(raw)
    except:
        return raw  # fallback (no recomendado, pero no rompe)

def _get_user_by_username(username):
    return User.query.filter_by(username=username).first()

def _get_user_by_email(email):
    return User.query.filter_by(email=email).first() if hasattr(User, "email") else None

def _set_password(u: User, raw: str):
    hashed = _hash_password(raw)
    if hasattr(u, "password_hash"):
        u.password_hash = hashed
    elif hasattr(u, "password"):
        u.password = hashed
    db.session.commit()

def _ensure_user(username, email, password, is_admin=False):
    u = _get_user_by_username(username) or (email and _get_user_by_email(email))
    if not u:
        kwargs = dict(username=username)
        if hasattr(User, "email"): kwargs["email"] = email
        if hasattr(User, "is_active"): kwargs["is_active"] = True
        if hasattr(User, "is_admin"):  kwargs["is_admin"]  = is_admin
        if hasattr(User, "password_hash"):
            kwargs["password_hash"] = _hash_password(password)
        else:
            kwargs["password"] = _hash_password(password)
        u = User(**kwargs)
        db.session.add(u)
        db.session.commit()
    else:
        _set_password(u, password)
    return u

def _require_bearer_token():
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Bearer "):
        return None
    return auth.split(" ",1)[1]

def _decode_jwt(token):
    # Si tienes una decodificación real en auth.py, la usamos
    try:
        from auth import decode_access
        return decode_access(token)
    except:
        # Fallback mínimo (permite avanzar en desarrollo)
        return {"sub": None, "roles": []}

def _me_user():
    token = _require_bearer_token()
    if not token:
        return None
    claims = _decode_jwt(token)
    if not claims or "sub" not in claims:
        return None
    return User.query.get(claims["sub"])

# --------------------- RUTAS ---------------------
def register_routes(app):
    @app.route("/orgs", methods=["POST"])
    def create_org():
        me = _me_user()
        if not me:
            return jsonify({"error":"unauthorized"}), 401
        data = request.get_json(force=True) or {}
        name = data.get("name")
        if not name or len(name) < 2:
            return jsonify({"error":"invalid name"}), 400
        org = Organization(name=name, status="active")
        db.session.add(org); db.session.commit()
        db.session.add(OrgMembership(user_id=me.id, org_id=org.id, role="owner"))
        db.session.commit()
        return jsonify({"id": org.id, "name": org.name, "status": org.status})

    @app.route("/orgs/<org_id>/users", methods=["POST"])
    def org_add_user(org_id):
        me = _me_user()
        if not me:
            return jsonify({"error":"unauthorized"}), 401
        org = Organization.query.get(org_id)
        if not org or org.status != "active":
            return jsonify({"error":"org not found"}), 404

        my_mem = OrgMembership.query.filter_by(user_id=me.id, org_id=org_id).first()
        if not my_mem or my_mem.role not in ("owner","manager"):
            return jsonify({"error":"forbidden"}), 403

        data = request.get_json(force=True) or {}
        username = data.get("username")
        role     = data.get("role","agent")
        if role not in ("owner","manager","agent","viewer","suspended"):
            return jsonify({"error":"invalid role"}), 400

        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({"error":"user not found"}), 404

        mem = OrgMembership.query.filter_by(user_id=user.id, org_id=org_id).first()
        if not mem:
            mem = OrgMembership(user_id=user.id, org_id=org_id, role=role)
            db.session.add(mem)
        else:
            mem.role = role
        db.session.commit()
        return jsonify({"username": user.username, "role": role})

    @app.route("/orgs/<org_id>/users", methods=["GET"])
    def org_list_users(org_id):
        me = _me_user()
        if not me:
            return jsonify({"error":"unauthorized"}), 401
        org = Organization.query.get(org_id)
        if not org or org.status != "active":
            return jsonify({"error":"org not found"}), 404
        my_mem = OrgMembership.query.filter_by(user_id=me.id, org_id=org_id).first()
        if not my_mem:
            return jsonify({"error":"forbidden"}), 403

        q = db.session.query(User.username, OrgMembership.role).join(
            OrgMembership, OrgMembership.user_id == User.id
        ).filter(OrgMembership.org_id == org_id)
        return jsonify([{"username": u, "role": r} for (u, r) in q.all()])

# --------------------- INICIALIZACIÓN ÚNICA ---------------------
def init(app):
    # crea tablas nuevas + usuarios semilla
    with app.app_context():
        db.create_all()
        admin_user = os.getenv("ADMIN_USERNAME", "tony")
        admin_email = os.getenv("ADMIN_EMAIL", "vtonyb@gmail.com")
        admin_pass  = os.getenv("ADMIN_PASSWORD", "Noa2025!")
        _ensure_user(admin_user, admin_email, admin_pass, True)
        _ensure_user("jeff",    "jeff@noa.seg",    "Noa2025!", False)
        _ensure_user("hermann", "hermann@noa.seg", "Noa2025!", False)
        print("[noa] seed OK (tony/jeff/hermann)")

    # registra rutas /orgs
    register_routes(app)

    # health (por si no existe)
    try:
        @app.route("/health")
        def _health():
            return {"ok": True}
    except Exception:
        pass
