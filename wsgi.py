# wsgi.py — Arranque a prueba de balas
import traceback

try:
    # Importa tu app real
    from app import app as _flask_app
    app = _flask_app
    print("[WSGI] app importada OK desde app:app")
except Exception as e:
    # Si algo truena, NO tumbamos el proceso:
    print("[WSGI] ERROR al importar app:app ->", e)
    traceback.print_exc()

    # Levantamos una app mínima que NO se cae y muestra el error en /health
    from flask import Flask, jsonify
    app = Flask(__name__)

    BOOT_ERROR = "".join(traceback.format_exc())

    @app.route("/health")
    def health():
        return jsonify(ok=False, boot_error=BOOT_ERROR), 200

    @app.route("/")
    def root():
        return jsonify(msg="App mínima viva. Revisa /health para el error."), 200
