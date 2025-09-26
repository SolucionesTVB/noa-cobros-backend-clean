# app.py — NOA Cobros (backend limpio)
import os, time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import bcrypt, jwt  # PyJWT

def _normalize_db_url(raw: str) -> str:
    if not raw: return "sqlite:///local.db"
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://") and "+psycopg" not in raw:
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw

DB_URL = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///local.db"))
JWT_SECRET = os.getenv("JWT_SECRET", "dev-inseguro-cambia-esto")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "changeme-admin")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DB_URL
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
CORS(app, resources={r"/*": {"origins": [FRONTEND_ORIGIN] if FRONTEND_ORIGIN else ["*"]}})

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Cobro(db.Model):
    __tablename__ = "cobro"
    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Float, nullable=False, default=0.0)
    descripcion = db.Column(db.String(255), nullable=False, default="")
    estado = db.Column(db.String(50), nullable=False, default="pendiente")  # pendiente|pagado
    referencia = db.Column(db.String(100), nullable=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

def ensure_user_columns():
    with app.app_context():
        try:
            db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);'))
            db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW();'))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"ensure_user_columns error: {e}")

def ensure_cobro_columns():
    with app.app_context():
        try:
            db.session.execute(text('ALTER TABLE "cobro" ADD COLUMN IF NOT EXISTS referencia VARCHAR(100);'))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"ensure_cobro_columns error: {e}")

def create_tables_once():
    with app.app_context():
        db.create_all()
        ensure_user_columns()
        ensure_cobro_columns()

def make_token(email: str) -> str:
    payload = {"sub": email, "exp": datetime.utcnow() + timedelta(hours=12), "iat": datetime.utcnow()}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def read_token(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "): return None
    token = auth_header.split(" ", 1)[1].strip()
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return data.get("sub")
    except Exception:
        return None

def require_auth():
    email = read_token(request.headers.get("Authorization", ""))
    if not email: return None, (jsonify({"error": "no_autorizado"}), 401)
    u = User.query.filter_by(email=email).first()
    if not u: return None, (jsonify({"error": "no_autorizado"}), 401)
    return u, None

@app.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"ok": True, "db": "on", "db_url_scheme": DB_URL.split(":", 1)[0]}), 200
    except Exception as e:
        return jsonify({"ok": False, "db": "off", "error": str(e)}), 200

@app.get("/__ok")
def __ok():
    try:
        routes = [str(r) for r in app.url_map.iter_rules()]
        return jsonify({
            "ok": True, "routes_count": len(routes),
            "has_stats": any("/stats" in r for r in routes),
            "version": os.getenv("APP_VERSION", "") or str(int(time.time()))
        }), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/admin/routes")
def admin_routes():
    if request.headers.get("X-Admin-Secret") != ADMIN_SECRET:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    routes = [{"rule": str(r), "methods": sorted(list(r.methods - {"HEAD", "OPTIONS"}))} for r in app.url_map.iter_rules()]
    return jsonify({"ok": True, "count": len(routes), "routes": routes})

@app.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "faltan_datos"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"ok": True, "detail": "ya_existe"}), 200
    try:
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        u = User(email=email, password_hash=pw_hash)
        db.session.add(u); db.session.commit()
        return jsonify({"ok": True, "id": u.id, "email": u.email}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500

@app.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "faltan_datos"}), 400
    u = User.query.filter_by(email=email).first()
    if not u or not getattr(u, "password_hash", None):
        return jsonify({"error": "credenciales_invalidas"}), 401
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), u.password_hash.encode("utf-8"))
    except Exception as e:
        return jsonify({"error": "bcrypt_error", "detail": str(e)}), 500
    if not ok:
        return jsonify({"error": "credenciales_invalidas"}), 401
    token = make_token(email)
    return jsonify({"access_token": token, "token_type": "bearer"}), 200

@app.get("/users")
def list_users():
    u, err = require_auth()
    if err: return err
    items = [{"id": x.id, "email": x.email} for x in User.query.order_by(User.id.asc()).limit(10).all()]
    if not items: items = [{"id": 1, "email": "demo@noa.com"}]
    return jsonify(items), 200

@app.get("/cobros")
def cobros_list():
    u, err = require_auth()
    if err: return err
    q = Cobro.query
    estado = request.args.get("estado")
    if estado: q = q.filter(Cobro.estado == estado)
    desde = request.args.get("desde"); hasta = request.args.get("hasta")
    if desde:
        try: q = q.filter(Cobro.creado_en >= datetime.fromisoformat(desde))
        except Exception: pass
    if hasta:
        try: q = q.filter(Cobro.creado_en <= datetime.fromisoformat(hasta))
        except Exception: pass
    q = q.order_by(Cobro.id.desc())
    items = [{
        "id": x.id, "monto": float(x.monto or 0.0), "descripcion": x.descripcion,
        "estado": x.estado, "referencia": x.referencia, "creado_en": x.creado_en.isoformat()
    } for x in q.all()]
    return jsonify(items), 200

@app.post("/cobros")
def cobros_create():
    u, err = require_auth()
    if err: return err
    data = request.get_json(silent=True) or {}
    try:
        c = Cobro(
            monto=float(data.get("monto") or 0.0),
            descripcion=(data.get("descripcion") or "").strip(),
            estado=(data.get("estado") or "pendiente").strip(),
            referencia=(data.get("referencia") or None)
        )
        db.session.add(c); db.session.commit()
        return jsonify({
            "id": c.id, "monto": c.monto, "descripcion": c.descripcion, "estado": c.estado,
            "referencia": c.referencia, "creado_en": c.creado_en.isoformat()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500

@app.get("/stats")
def stats():
    u, err = require_auth()
    if err: return err
    q = Cobro.query
    desde = request.args.get("desde"); hasta = request.args.get("hasta"); estado = request.args.get("estado")
    if desde:
        try: q = q.filter(Cobro.creado_en >= datetime.fromisoformat(desde))
        except Exception: pass
    if hasta:
        try: q = q.filter(Cobro.creado_en <= datetime.fromisoformat(hasta))
        except Exception: pass
    if estado: q = q.filter(Cobro.estado == estado)
    items = q.all()
    total = sum(float(x.monto or 0.0) for x in items)
    count = len(items)
    pagados = sum(1 for x in items if x.estado == "pagado")
    pendientes = sum(1 for x in items if x.estado == "pendiente")
    return jsonify({"count": count, "total": total, "pagados": pagados, "pendientes": pendientes}), 200

create_tables_once()
