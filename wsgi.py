# wsgi.py — Wrapper que **siempre** levanta el server y registra rutas clave
import traceback

try:
    # 1) importa tu app real
    from app import app as _flask_app
    app = _flask_app
    print("[WSGI] app importada OK desde app:app")

    # 2) registra /auth/login aunque NO lo hayas hecho en app.py
    try:
        from simple_auth import register_auth, decode_access
        register_auth(app)
        print("[WSGI] /auth/login registrado (simple_auth)")
    except Exception as e:
        print("[WSGI] simple_auth no disponible:", e)

    # 3) inicia plugin de orgs aunque NO esté llamado en app.py
    try:
        import noa_multitenant_plugin as NOA
        NOA.init(app)
        print("[WSGI] NOA.init(app) OK")
    except Exception as e:
        print("[WSGI] NOA.init ERROR:", e)
        traceback.print_exc()

    # 4) health por si no existe
    try:
        @app.route("/health")
        def _health():
            return {"ok": True}
    except Exception:
        pass

except Exception as e:
    # Si NO pudo importar app:app, no tumbes el proceso — muestra el error en /health
    print("[WSGI] ERROR al importar app:app ->", e)
    traceback.print_exc()

    from flask import Flask, jsonify
    app = Flask(__name__)
    BOOT_ERROR = "".join(traceback.format_exc())

    @app.route("/health")
    def health():
        return jsonify(ok=False, boot_error=BOOT_ERROR), 200

    @app.route("/")
    def root():
        return jsonify(msg="App mínima viva. Revisa /health para el error."), 200


 
