from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
import os

# instancia global (para from app import db)
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

    # --- DB ---
    url = _normalize_db_url(os.getenv("DATABASE_URL", 
"sqlite:///local.db"))
    app.config["SQLALCHEMY_DATABASE_URI"] = url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    # >>> CREA TABLAS SI NO EXISTEN <<<
    with app.app_context():
        db.create_all()

    @app.get("/health")
    def health():
        return jsonify(ok=True)

    # --- Auth/JWT ---
    from flask_jwt_extended import JWTManager
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", 
"noa_jwt_2025_super")
    JWTManager(app)

    from auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    return app


    # --- DB ---
    url = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///local.db"))
    app.config["SQLALCHEMY_DATABASE_URI"] = url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    @app.get("/health")
    def health():
        return jsonify(ok=True)

    # --- Auth/JWT y blueprint /auth ---
    from flask_jwt_extended import JWTManager
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "noa_jwt_2025_super")
    JWTManager(app)

    from auth import bp as auth_bp
    app.register_blueprint(auth_bp)
    # --- fin auth ---

    return app

# necesario para gunicorn: "app:app"
app = create_app()
