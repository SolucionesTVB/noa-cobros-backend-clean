from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
import os

# Instancia global para que models pueda hacer: from app import db
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # DB (Render usa DATABASE_URL). Local: SQLite.
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///local.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Inicializa SQLAlchemy con la app
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

# Necesario para gunicorn "app:app"
app = create_app()
