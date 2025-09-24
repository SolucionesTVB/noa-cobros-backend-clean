import os
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text

db = SQLAlchemy()

def _normalize_db_url(raw: str) -> str:
    if not raw:
        return "sqlite:///local.db"
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://") and "+psycopg" not in raw:
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw

app = Flask(__name__)
CORS(app)

url = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///local.db"))
app.config["SQLALCHEMY_DATABASE_URI"] = url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# ===== MODELOS =====
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)

class Cobro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Numeric(10,2), nullable=False)
    descripcion = db.Column(db.String(255))
    estado = db.Column(db.String(20), nullable=False, default="pendiente")  # pendiente|pagado|cancelado
    creado_en = db.Column(db.DateTime, server_default=db.func.now())

with app.app_context():
    try:
        db.create_all()  # crea tablas si no existen
    except Exception:
        pass

# ===== HEALTH =====
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

# ===== AUTH DEMO =====
@app.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()
    demo_email = os.getenv("DEMO_EMAIL")
    demo_pass = os.getenv("DEMO_PASSWORD")
    if demo_email is not None and demo_pass is not None:
        if email != demo_email or password != demo_pass:
            return jsonify({"error": "credenciales inválidas"}), 401
    if not email or not password:
        return jsonify({"error": "faltan campos"}), 400
    return jsonify({"access_token": "demo-token", "token_type": "bearer"}), 200

def _require_token():
    auth = request.headers.get("Authorization", "")
    return auth.strip() == "Bearer demo-token"

# ===== USERS =====
@app.get("/users")
def list_users():
    if not _require_token():
        return jsonify({"error": "no autorizado"}), 401
    try:
        users = User.query.order_by(User.id.asc()).limit(10).all()
        if not users:
            return jsonify([{"id": 1, "email": "demo@noa.com"}]), 200
        return jsonify([{"id": u.id, "email": u.email} for u in users]), 200
    except Exception as e:
        return jsonify({"error": "db_error", "detail": str(e)}), 500

# ===== COBROS =====
@app.get("/cobros")
def get_cobros():
    if not _require_token():
        return jsonify({"error": "no autorizado"}), 401
    cobros = Cobro.query.order_by(Cobro.id.desc()).all()
    return jsonify([
        {
            "id": c.id,
            "monto": float(c.monto) if c.monto is not None else 0.0,
            "descripcion": c.descripcion,
            "estado": c.estado,
            "creado_en": c.creado_en.isoformat() if c.creado_en else None
        }
        for c in cobros
    ]), 200

@app.post("/cobros")
def crear_cobro():
    if not _require_token():
        return jsonify({"error": "no autorizado"}), 401
    data = request.get_json(silent=True) or {}
    # Validaciones simples (modo 8 años)
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
