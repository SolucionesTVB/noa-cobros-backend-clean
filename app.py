from flask import Flask, request, jsonify
<<<<<<< HEAD
import sqlite3

app = Flask(__name__)

# --- Base de datos ---
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute(
        """CREATE TABLE IF NOT EXISTS facturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            monto REAL,
            vence TEXT,
            estado TEXT DEFAULT 'pendiente',
            telefono TEXT,
            email TEXT,
            canal TEXT,
            notas TEXT
        )"""
    )
    db.commit()

# --- Rutas principales ---

=======

app = Flask(__name__)

# Página principal (bienvenida)
>>>>>>> c7d68f0 (replace full backend app with clean version)
@app.route("/")
def home():
    return """
    <html>
      <head>
        <title>N – Backend</title>
        <style>
          body { font-family: Arial, sans-serif; background: #0d1117; 
color: #fff; text-align: center; padding: 50px; }
          h1 { color: #00d4ff; text-shadow: 0 0 10px #00d4ff; font-size: 
48px; }
          p { font-size: 18px; line-height: 1.5; }
          b { color: #00ff88; }
          a { color: #00ff88; font-size: 18px; text-decoration: none; }
          a:hover { text-shadow: 0 0 5px #00ff88; }
        </style>
      </head>
      <body>
        <h1>N</h1>
        <p><b>Bienvenido al backend de NOA Cobros</b></p>
        <p><b>Este es el motor en Render</b>, encargado de procesar 
facturas y enviar notificaciones.</p>
        <p>La interfaz de usuario está en:<br>
          <a href="https://polite-gumdrop-ba6be7.netlify.app" 
target="_blank">
            👉 Ir al Frontend de NOA Cobros
          </a>
        </p>
        <p style="margin-top:30px; font-size:12px; color:#aaa;">
          Marca blanca – Listo para producción
        </p>
      </body>
    </html>
    """

<<<<<<< HEAD
@app.route("/facturas", methods=["GET", "POST"])
def facturas():
    db = get_db()
    if request.method == "POST":
        data = request.get_json(force=True)
        if isinstance(data, dict):
            data = [data]
        for factura in data:
            db.execute(
                "INSERT INTO facturas (cliente, monto, vence, telefono, email, canal, notas) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    factura.get("cliente"),
                    factura.get("monto"),
                    factura.get("vence"),
                    factura.get("telefono"),
                    factura.get("email"),
                    factura.get("canal"),
                    factura.get("notas"),
                ),
            )
        db.commit()
        return jsonify({"ok": True})
    else:
        rows = db.execute("SELECT * FROM facturas").fetchall()
        return jsonify([dict(row) for row in rows])

@app.route("/notificar", methods=["POST"])
def notificar():
    data = request.get_json(force=True)
    ids = data.get("ids", [])
    enviados = []
    for factura_id in ids:
        enviados.append({"id": factura_id, "resp": {"success": True}})
    return jsonify({"ok": True, "enviados": enviados})

@app.route("/facturas/clear", methods=["POST"])
def clear_facturas():
    try:
        db = get_db()
        db.execute("DELETE FROM facturas")
        db.commit()
        return jsonify({"ok": True, "msg": "Todas las facturas borradas"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# --- Inicializar DB ---
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
=======
# Lista de facturas en memoria
facturas = []

# GET: listar facturas
@app.route("/facturas", methods=["GET"])
def get_facturas():
    return jsonify(facturas)

# POST: agregar facturas
@app.route("/facturas", methods=["POST"])
def add_facturas():
    data = request.get_json()
    if isinstance(data, list):
        for f in data:
            f["id"] = len(facturas) + 1
            facturas.append(f)
        return jsonify({"ok": True, "msg": "Facturas agregadas", "count": 
len(data)})
    return jsonify({"error": "Formato inválido"}), 400

# DELETE: borrar todas las facturas
@app.route("/facturas/clear", methods=["POST"])
def clear_facturas():
    facturas.clear()
    return jsonify({"ok": True, "msg": "Todas las facturas borradas"})

# POST: notificar facturas
@app.route("/notificar", methods=["POST"])
def notificar():
    data = request.get_json()
    ids = data.get("ids", [])
    enviados = [f for f in facturas if f.get("id") in ids]
    return jsonify({"ok": True, "enviados": enviados})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

>>>>>>> c7d68f0 (replace full backend app with clean version)
