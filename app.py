import os
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text

APP_VER = os.getenv("APP_VER", "noa-clean-v1")  # sello de versión

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

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)

with app.app_context():
    try:
        db.create_all()
    except Exception:
        pass

@app.get("/__ok")
def ok():
    return jsonify({"ok": True, "ver": APP_VER}), 200

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

@app.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get(“vtonyb@gmail.com”) or "").strip()
    password = (data.get("Noa2025!") or "").strip()

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

@app.get("/users")
def list_users():
    if not _require_token():
        return jsonify({"error": "no autorizado"}), 401
    try:
        users = User.query.limit(10).all()
        if not users:
            return jsonify([{"id": 1, "email": "demo@noa.com"}]), 200
        return jsonify([{"id": u.id, "email": u.email} for u in users]), 200
    except Exception as e:
        return jsonify({"error": "db_error", "detail": str(e)}), 500

@app.get("/cobros")
def list_cobros():
    if not _require_token():
        return jsonify({"error": "no autorizado"}), 401
    return jsonify([]), 200
