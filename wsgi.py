# wsgi.py — Arranque a prueba de balas + /auth/login garantizado
import traceback, os, time
from flask import jsonify, request

try:
    # 1) Importa tu app real desde app.py
    from app import app as _flask_app
    app = _flask_app
    print("[WSGI] app importada OK desde app:app")

    # 2) Intenta registrar /auth/login desde simple_auth.py (si existe)
    try:
        from simple_auth import register_auth, decode_access  # opcional
        register_auth(app)
        print("[WSGI] /auth/login registrado via simple_auth")
    except Exception as e:
        print("[WSGI] simple_auth no disponible:", e)

    # 3) Si NO existe /auth/login aún, créalo aquí mismo (fallback)
    def _has_auth_login():
        try:
            for rule in app.url_map.iter_rules():
                if rule.rule == "/auth/login" and "POST" in (rule.methods or []):
                    return True
        except Exception:
            pass
        return False

    if not _has_auth_login():
        print("[WSGI] /auth/login no encontrado, creando fallback en wsgi.py")
        # Dependencias mínimas para verificar usuario y clave
        from itsdangerous import URLSafeTimedSerializer
        from werkzeug.security import check_password_hash
        from models import db, User  # tu modelo User y la DB

        def _ser():
            secret = os.getenv("JWT_SECRET_KEY", "change-me")
            return URLSafeTimedSerializer(secret_key=secret, salt="noa-auth")

        def _mk_token(user_id):
            s = _ser()
            return s.dumps({"sub": str(user_id), "iat": int(time.time())})

        def _password_ok(u, raw):
            # Soporta password_hash (hash) o password en claro
            if hasattr(u, "password_hash") and u.password_hash:
                try:
                    return check_password_hash(u.password_hash, raw)
                except Exception:
                    pass
            if hasattr(u, "password") and u.password:
                return u.password == raw
            return False

        @app.route("/auth/login", methods=["POST"])
        def _login_fallback():
            data = request.get_json(silent=True) or {}
            username = data.get("username") or data.get("user") or data.get("login")
            password = data.get("password") or data.get("pass") or data.get("pwd")
            if not username or not password:
                return jsonify({"error":"username/password requeridos"}), 400
            u = User.query.filter_by(username=username).first()
            if not u or not _password_ok(u, password):
                return jsonify({"error":"credenciales inválidas"}), 401
            token = _mk_token(u.id)
            return jsonify({"access_token": token, "token_type":"bearer",
                            "user":{"id":u.id, "username":u.username}})

    # 4) Intenta inicializar rutas de organizaciones (si existe el plugin)
    try:
        import noa_multitenant_plugin as NOA  # opcional
        NOA.init(app)
        print("[WSGI] NOA.init(app) OK")
    except Exception as e:
        print("[WSGI] NOA.init ERROR:", e)
        traceback.print_exc()

    # 5) /health por si no existe
    try:
        @app.route("/health")
        def _health_ok():
            return {"ok": True}
    except Exception:
        pass

except Exception as e:
    # Si falló importar app:app, NO tumbamos el proceso y mostramos el error en /health
    print("[WSGI] ERROR al importar app:app ->", e)
    traceback.print_exc()
    from flask import Flask
    app = Flask(__name__)
    BOOT_ERROR = "".join(traceback.format_exc())

    @app.route("/health")
    def health():
        return jsonify(ok=False, boot_error=BOOT_ERROR), 200

    @app.route("/")
    def root():
        return jsonify(msg="App mínima viva. Revisa /health para el error."), 200
