from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
import os, traceback, sys


# instancia global (para "from app import db")
db = SQLAlchemy()

def _normalize_db_url(raw: str) -> str:
    if not raw:
        return "sqlite:///local.db"
    # Render suele dar 'postgres://...' o 'postgresql://...'
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://") and "+psycopg" not in raw:
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw

def create_app():
    app = Flask(__name__)
    import noa_multitenant_plugin as NOA
NOA.init(app)

    # seed al arrancar (crea/actualiza tony/jeff/hermann)
@app.before_first_request
def _seed():
    seed_startup()

# registrar las rutas /orgs
register_org_routes(app)

    app.config["PROPAGATE_EXCEPTIONS"] = True

    # --- DB ---
    url = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///local.db"))
    app.config["SQLALCHEMY_DATABASE_URI"] = url
# ⬇️ IMPORTAR DESPUÉS de crear app y db
from seed_startup import seed_startup
from org_routes import register_org_routes

# Seed al arrancar
@app.before_first_request
def _seed():
    seed_startup()

# Registrar rutas /orgs
register_org_routes(app)

# Health (por si no existe)
@app.route("/health")
def health():
    return {"ok": True}

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    # Importar modelos y crear tablas
    with app.app_context():
        import models  # registra clases
        db.create_all()

    @app.errorhandler(Exception)
    def _app_error(e):
        tb = traceback.format_exc()
        print("=== APP ERROR ===", file=sys.stderr)
        print(tb, file=sys.stderr)
        # Devolver JSON con detalle en vez de HTML
        return jsonify({"error":"exception","detail":str(e)}), 500

    @app.get("/health")
    def health():
        return jsonify(ok=True)

    # --- Auth/JWT ---
    from flask_jwt_extended import JWTManager
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "noa_jwt_2025_super")
    JWTManager(app)

    from auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    # ruta sencilla para confirmar que la app vive
    @app.get("/_echo")
    def _echo():
        return jsonify(ok=True, msg="app viva")

    return app

# necesario para gunicorn: "app:app"
app = create_app()
# === NOA: inicialización segura (no revienta el deploy si algo falla) ===
try:
    import noa_multitenant_plugin as NOA
    NOA.init(app)
    print("[NOA] init OK")
except Exception as e:
    import traceback
    print("[NOA] init ERROR:", e)
    traceback.print_exc()

# Health por si aún no existe
try:
    @app.route("/health")
    def _health():
        return {"ok": True}
except Exception:
    pass
# === NOA: inicialización segura (no tumba el deploy si algo falla) ===
try:
    import noa_multitenant_plugin as NOA
    NOA.init(app)
    print("[NOA] init OK")
except Exception as e:
    import traceback
    print("[NOA] init ERROR:", e)
    traceback.print_exc()

# Health por si no existe
try:
    @app.route("/health")
    def _health():
        return {"ok": True}
except Exception:
    pass

