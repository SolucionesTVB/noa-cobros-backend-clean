# app.py
import os
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)

# CORS: permití el frontend real desde env
CORS(app, resources={r"/*": {"origins": os.getenv("CORS_ORIGIN", "*")}})

@app.get("/health")
def health():
    return jsonify(status="ok")

# Endpoints mínimos para probar que vive
@app.get("/")
def root():
    return jsonify(service="noa-cobros-backend", ok=True)

@app.get("/invoices")
def invoices():
    # responder 401 si luego activás auth; por ahora devolvemos demo
    return jsonify(total=0, items=[])
