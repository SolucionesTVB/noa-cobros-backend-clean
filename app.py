import os, datetime
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text
import bcrypt, jwt

db = SQLAlchemy()

def _normalize_db_url(raw: str) -> str:
    if not raw:
        return "sqlite:///local.db"
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://") and "+psycopg" not in raw:
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw

# ==== APP / CONFIG ====
app = Flask(__name__)
CORS(app)
url = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///local.db"))
app.config["SQLALCHEMY_DATABASE_URI"] = url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
JWT_SECRET = os.getenv("JWT_SECRET", "CÁMBIAME-POR-FAVOR")  # 🔐 PÓN TODO EN RENDER
JWT_ALG = "HS256"
JWT_EXP_MIN = int(os.getenv("JWT_EXP_MIN", "1440"))  # 24 horas

db.init_app(app)

# ==== MODELOS ====
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    creado_en = db.Column(db.DateTime, server_default=db.func.now())

class Cobro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(255))
    estado = db.Column(db.String(20), nullable=False, default="pendiente")  # pendiente|pagado|cancelado
    creado_en = db.Column(db.DateTime, server_default=db.func.now())

with app.app_context():
    try:
        db.create_all()
    except Exception:
        pass


# ==== AUTO-MIGRATIONS (Alembic) ====
if os.getenv("RUN_DB_MIGRATIONS") == "1":
    try:
        from alembic.config import Config as _AlbConfig
        from alembic import command as _alb_command
        _cfg = _AlbConfig(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        # Asegurar que Alembic use la misma URL normalizada de la app
        _cfg.set_main_option("sqlalchemy.url", url)
        with app.app_context():
            _alb_command.upgrade(_cfg, "head")
        print("Alembic auto-migrations: OK (upgrade head)")
    except Exception as _e:
        print("Alembic auto-migrations: ERROR ->", _e)
# ==== FIN AUTO-MIGRATIONS ====

# ==== UTILS AUTH ====
def _make_token(user_id: int, email: str) -> str:
    now = datetime.datetime.utcnow()
    payload = {"sub": str(user_id), "email": email, "iat": now, "exp": now + datetime.timedelta(minutes=JWT_EXP_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def _get_current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = int(payload.get("sub", "0"))
        user = User.query.get(uid)
        return user
    except Exception:
        return None

def _require_user():
    user = _get_current_user()
    if not user:
        return None, (jsonify({"error": "no_autorizado"}), 401)
    return user, None

# ==== HEALTH ====
@app.get("/health")
def health():
    ok_db = False
    err = None
    try:
        db.session.execute(text("SELECT 1"))
        ok_db = True
    except Exception as e:
        err = str(e)
    return jsonify({
        "ok": ok_db,
        "db": "on" if ok_db else "off",
        "status": "healthy" if ok_db else "degraded",
        "db_url_scheme": url.split(":")[0] if ":" in url else url,
        "error": err
    }), 200

# ==== AUTH REAL ====
@app.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    if not email or not password:
        return jsonify({"error": "faltan_campos"}), 400
    if len(password) < 6:
        return jsonify({"error": "password_corta"}), 400

    try:
        # ¿Existe?
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "email_ya_existe"}), 409
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        u = User(email=email, password_hash=pw_hash)
        db.session.add(u)
        db.session.commit()
        return jsonify({"id": u.id, "email": u.email}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500

@app.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    if not email or not password:
        return jsonify({"error": "faltan_campos"}), 400
    u = User.query.filter_by(email=email).first()
    if not u:
        return jsonify({"error": "credenciales_invalidas"}), 401
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), u.password_hash.encode("utf-8"))
    except Exception:
        ok = False
    if not ok:
        return jsonify({"error": "credenciales_invalidas"}), 401

    token = _make_token(u.id, u.email)
    return jsonify({"access_token": token, "token_type": "bearer"}), 200

# ==== USERS (demo) ====
@app.get("/users")
def list_users():
    user, err = _require_user()
    if err: return err
    users = User.query.order_by(User.id.asc()).limit(50).all()
    return jsonify([{"id": u.id, "email": u.email} for u in users]), 200

# ==== COBROS ====
@app.get("/cobros")
def get_cobros():
    user, err = _require_user()
    if err: return err
    estado = request.args.get("estado", "", type=str).strip().lower()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    if page < 1: page = 1
    if page_size < 1: page_size = 20
    if page_size > 100: page_size = 100

    q = Cobro.query
    if estado in ("pendiente", "pagado", "cancelado"):
        q = q.filter(Cobro.estado == estado)

    total = q.count()
    items = q.order_by(Cobro.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return jsonify({
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "id": c.id,
                "monto": float(c.monto) if c.monto is not None else 0.0,
                "descripcion": c.descripcion,
                "estado": c.estado,
                "creado_en": c.creado_en.isoformat() if c.creado_en else None
            } for c in items
        ]
    }), 200

@app.post("/cobros")
def crear_cobro():
    user, err = _require_user()
    if err: return err
    data = request.get_json(silent=True) or {}
    try:
        monto = float(data.get("monto", 0))
    except Exception:
        return jsonify({"error": "monto_invalido"}), 400
    if monto <= 0:
        return jsonify({"error": "monto_debe_ser_positivo"}), 400
    descripcion = (data.get("descripcion") or "").strip() or None
    estado = (data.get("estado") or "pendiente").strip().lower()
    if estado not in ("pendiente", "pagado", "cancelado"):
        return jsonify({"error": "estado_invalido"}), 400

    try:
        db.create_all()
        nuevo = Cobro(monto=monto, descripcion=descripcion, estado=estado)
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({
            "id": nuevo.id,
            "monto": float(nuevo.monto),
            "descripcion": nuevo.descripcion,
            "estado": nuevo.estado,
            "creado_en": nuevo.creado_en.isoformat() if nuevo.creado_en else None
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500

@app.patch("/cobros/<int:cobro_id>")
def actualizar_cobro(cobro_id: int):
    user, err = _require_user()
    if err: return err
    data = request.get_json(silent=True) or {}
    estado = data.get("estado")
    descripcion = data.get("descripcion")
    if estado is None and descripcion is None:
        return jsonify({"error": "nada_para_actualizar"}), 400
    if estado is not None:
        estado = str(estado).strip().lower()
        if estado not in ("pendiente", "pagado", "cancelado"):
            return jsonify({"error": "estado_invalido"}), 400
    c = Cobro.query.get(cobro_id)
    if not c:
        return jsonify({"error": "no_encontrado"}), 404
    try:
        if estado is not None: c.estado = estado
        if descripcion is not None: c.descripcion = (descripcion or "").strip() or None
        db.session.commit()
        return jsonify({
            "id": c.id, "monto": float(c.monto),
            "descripcion": c.descripcion, "estado": c.estado,
            "creado_en": c.creado_en.isoformat() if c.creado_en else None
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500

@app.delete("/cobros/<int:cobro_id>")
def borrar_cobro(cobro_id: int):
    user, err = _require_user()
    if err: return err
    c = Cobro.query.get(cobro_id)
    if not c:
        return jsonify({"error": "no_encontrado"}), 404
    try:
        db.session.delete(c)
        db.session.commit()
        return jsonify({"ok": True, "id": cobro_id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500
