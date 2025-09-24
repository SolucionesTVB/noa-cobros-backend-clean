import os, datetime, io, csv
from flask import Flask, jsonify, request, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text
import bcrypt, jwt

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

# === CORS: solo tu frontend, docs públicos ===
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")  # p.ej. https://polite-gumdrop-ba6be7.netlify.app
CORS(app, resources={
    r"/docs": {"origins": "*"},
    r"/openapi.json": {"origins": "*"},
    r"/health": {"origins": "*"},
    r"/*": {"origins": FRONTEND_ORIGIN}
}, supports_credentials=False)

url = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///local.db"))
app.config["SQLALCHEMY_DATABASE_URI"] = url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
JWT_SECRET = os.getenv("JWT_SECRET", "CÁMBIAME-POR-FAVOR")
JWT_ALG = "HS256"
JWT_EXP_MIN = int(os.getenv("JWT_EXP_MIN", "1440"))

db.init_app(app)

# ===== MODELOS =====
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    creado_en = db.Column(db.DateTime, server_default=db.func.now())

class Cobro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(255))
    referencia = db.Column(db.String(50))
    estado = db.Column(db.String(20), nullable=False, default="pendiente")  # pendiente|pagado|cancelado
    creado_en = db.Column(db.DateTime, server_default=db.func.now())

with app.app_context():
    try:
        db.create_all()
    except Exception:
        pass

# ==== UTILS AUTH ====
def _make_token(user_id: int, email: str) -> str:
    now = datetime.datetime.utcnow()
    payload = {"sub": str(user_id), "email": email, "iat": now, "exp": now + datetime.timedelta(minutes=JWT_EXP_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def _get_current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = int(payload.get("sub", "0"))
        return User.query.get(uid)
    except Exception:
        return None

def _require_user():
    user = _get_current_user()
    if not user:
        return None, (jsonify({"error": "no_autorizado"}), 401)
    return user, None

@app.before_request
def _strict_origin():
    if FRONTEND_ORIGIN == "*" or request.method == "OPTIONS":
        return
    path = request.path or ""
    publico = path.startswith("/docs") or path.startswith("/openapi.json") or path.startswith("/health")
    if publico:
        return
    origin = request.headers.get("Origin", "")
    if origin and origin != FRONTEND_ORIGIN:
        return jsonify({"error": "origin_no_permitido"}), 403

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

# ===== AUTH REAL =====
@app.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    if not email or not password:
        return jsonify({"error": "faltan_campos"}), 400
    if len(password) < 6:
        return jsonify({"error": "password_corta"}), 400
    try:
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "email_ya_existe"}), 409
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        u = User(email=email, password_hash=pw_hash)
        db.session.add(u)
        db.session.commit()
        return jsonify({"id": u.id, "email": u.email}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500

@app.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    if not email or not password:
        return jsonify({"error": "faltan_campos"}), 400
    u = User.query.filter_by(email=email).first()
    if not u:
        return jsonify({"error": "credenciales_invalidas"}), 401
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), u.password_hash.encode("utf-8"))
    except Exception:
        ok = False
    if not ok:
        return jsonify({"error": "credenciales_invalidas"}), 401
    token = _make_token(u.id, u.email)
    return jsonify({"access_token": token, "token_type": "bearer"}), 200

# ===== COBROS =====
def _parse_int(value, default):
    try:
        v = int(value)
        return v if v > 0 else default
    except Exception:
        return default

def _parse_date(s):
    """YYYY-MM-DD -> datetime (inicio del día). Si vacío o mal, devuelve None."""
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None

@app.get("/cobros")
def get_cobros():
    user, err = _require_user()
    if err: return err

    # Filtros básicos
    estado = request.args.get("estado", "", type=str).strip().lower()
    desde_str = request.args.get("desde", "", type=str).strip()
    hasta_str = request.args.get("hasta", "", type=str).strip()
    page = _parse_int(request.args.get("page", 1), 1)
    page_size = _parse_int(request.args.get("page_size", 20), 20)
    if page_size > 100: page_size = 100

    q = Cobro.query
    if estado in ("pendiente", "pagado", "cancelado"):
        q = q.filter(Cobro.estado == estado)

    # Filtro por fechas (incluye día completo)
    d_desde = _parse_date(desde_str)
    d_hasta = _parse_date(hasta_str)
    if d_desde:
        q = q.filter(Cobro.creado_en >= d_desde)
    if d_hasta:
        fin = d_hasta + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
        q = q.filter(Cobro.creado_en <= fin)

    total = q.count()
    items = q.order_by(Cobro.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return jsonify({
        "page": page, "page_size": page_size, "total": total,
        "items": [{
            "id": c.id, "monto": float(c.monto) if c.monto is not None else 0.0,
            "descripcion": c.descripcion, "referencia": c.referencia,
            "estado": c.estado, "creado_en": c.creado_en.isoformat() if c.creado_en else None
        } for c in items]
    }), 200

@app.post("/cobros")
def crear_cobro():
    user, err = _require_user()
    if err: return err
    data = request.get_json(silent=True) or {}
    try:
        monto = float(data.get("monto", 0))
    except Exception:
        return jsonify({"error": "monto_invalido"}), 400
    if monto <= 0:
        return jsonify({"error": "monto_debe_ser_positivo"}), 400
    descripcion = (data.get("descripcion") or "").strip() or None
    referencia = (data.get("referencia") or "").strip() or None
    estado = (data.get("estado") or "pendiente").strip().lower()
    if estado not in ("pendiente", "pagado", "cancelado"):
        return jsonify({"error": "estado_invalido"}), 400
    try:
        db.create_all()
        nuevo = Cobro(monto=monto, descripcion=descripcion, referencia=referencia, estado=estado)
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({
            "id": nuevo.id, "monto": float(nuevo.monto),
            "descripcion": nuevo.descripcion, "referencia": nuevo.referencia,
            "estado": nuevo.estado, "creado_en": nuevo.creado_en.isoformat() if nuevo.creado_en else None
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500

@app.patch("/cobros/<int:cobro_id>")
def actualizar_cobro(cobro_id: int):
    user, err = _require_user()
    if err: return err
    data = request.get_json(silent=True) or {}
    estado = data.get("estado")
    descripcion = data.get("descripcion")
    referencia = data.get("referencia")
    if estado is None and descripcion is None and referencia is None:
        return jsonify({"error": "nada_para_actualizar"}), 400
    if estado is not None:
        estado = str(estado).strip().lower()
        if estado not in ("pendiente", "pagado", "cancelado"):
            return jsonify({"error": "estado_invalido"}), 400
    c = Cobro.query.get(cobro_id)
    if not c:
        return jsonify({"error": "no_encontrado"}), 404
    try:
        if estado is not None: c.estado = estado
        if descripcion is not None: c.descripcion = (descripcion or "").strip() or None
        if referencia is not None: c.referencia = (referencia or "").strip() or None
        db.session.commit()
        return jsonify({
            "id": c.id, "monto": float(c.monto),
            "descripcion": c.descripcion, "referencia": c.referencia,
            "estado": c.estado, "creado_en": c.creado_en.isoformat() if c.creado_en else None
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500

@app.delete("/cobros/<int:cobro_id>")
def borrar_cobro(cobro_id: int):
    user, err = _require_user()
    if err: return err
    c = Cobro.query.get(cobro_id)
    if not c:
        return jsonify({"error": "no_encontrado"}), 404
    try:
        db.session.delete(c)
        db.session.commit()
        return jsonify({"ok": True, "id": cobro_id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "db_error", "detail": str(e)}), 500

# ===== EXPORT CSV =====
@app.get("/cobros/export.csv")
def export_cobros_csv():
    user, err = _require_user()
    if err: return err

    estado = request.args.get("estado", "", type=str).strip().lower()
    desde_str = request.args.get("desde", "", type=str).strip()
    hasta_str = request.args.get("hasta", "", type=str).strip()

    q = Cobro.query
    if estado in ("pendiente", "pagado", "cancelado"):
        q = q.filter(Cobro.estado == estado)

    d_desde = _parse_date(desde_str)
    d_hasta = _parse_date(hasta_str)
    if d_desde:
        q = q.filter(Cobro.creado_en >= d_desde)
    if d_hasta:
        fin = d_hasta + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
        q = q.filter(Cobro.creado_en <= fin)

    rows = q.order_by(Cobro.id.desc()).all()

    # Construir CSV en memoria
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "monto", "descripcion", "referencia", "estado", "creado_en"])
    for c in rows:
        w.writerow([
            c.id,
            (float(c.monto) if c.monto is not None else 0.0),
            (c.descripcion or ""),
            (c.referencia or ""),
            c.estado,
            (c.creado_en.isoformat() if c.creado_en else "")
        ])

    out = make_response(buf.getvalue())
    out.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"cobros_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    out.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return out, 200

# ====== OPENAPI (Swagger UI) ======
def _openapi_spec():
    return {
        "openapi": "3.0.3",
        "info": {"title": "NOA Cobros API", "version": "1.1.0"},
        "servers": [{"url": "/"}],
        "paths": {
            "/health": {"get": {"summary": "Health", "responses": {"200": {"description": "OK"}}}},
            "/auth/register": {"post": {"summary": "Registrar usuario","responses": {"201":{"description":"Creado"}}}},
            "/auth/login": {"post": {"summary": "Login (JWT)","responses": {"200":{"description":"OK"}}}},
            "/users": {"get": {"summary": "Listar usuarios","security": [{"bearerAuth": []}],"responses": {"200":{"description":"OK"}}}},
            "/cobros": {
                "get": {"summary": "Listar cobros","security":[{"bearerAuth":[]}],
                        "parameters":[
                            {"name":"estado","in":"query","schema":{"type":"string","enum":["pendiente","pagado","cancelado"]}},
                            {"name":"desde","in":"query","schema":{"type":"string","example":"2025-09-01"}},
                            {"name":"hasta","in":"query","schema":{"type":"string","example":"2025-09-30"}},
                            {"name":"page","in":"query","schema":{"type":"integer","minimum":1}},
                            {"name":"page_size","in":"query","schema":{"type":"integer","minimum":1,"maximum":100}}
                        ],
                        "responses":{"200":{"description":"OK"}}},
                "post":{"summary":"Crear cobro","security":[{"bearerAuth":[]}],
                        "responses":{"201":{"description":"Creado"}}}
            },
            "/cobros/{id}": {
                "patch":{"summary":"Actualizar cobro","security":[{"bearerAuth":[]}],
                         "parameters":[{"name":"id","in":"path","required":True,"schema":{"type":"integer"}}],
                         "responses":{"200":{"description":"OK"},"404":{"description":"No encontrado"}}},
                "delete":{"summary":"Borrar cobro","security":[{"bearerAuth":[]}],
                          "parameters":[{"name":"id","in":"path","required":True,"schema":{"type":"integer"}}],
                          "responses":{"200":{"description":"OK"},"404":{"description":"No encontrado"}}}
            },
            "/cobros/export.csv": {
                "get": {"summary":"Exportar cobros a CSV","security":[{"bearerAuth":[]}],
                        "parameters":[
                            {"name":"estado","in":"query","schema":{"type":"string","enum":["pendiente","pagado","cancelado"]}},
                            {"name":"desde","in":"query","schema":{"type":"string","example":"2025-09-01"}},
                            {"name":"hasta","in":"query","schema":{"type":"string","example":"2025-09-30"}}
                        ],
                        "responses":{"200":{"description":"CSV"}}}
            }
        },
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}}
    }

@app.get("/openapi.json")
def openapi_json():
    return jsonify(_openapi_spec())

@app.get("/docs")
def docs():
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>NOA Cobros — Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist/swagger-ui.css">
  <style>body {{ margin:0; }} #swagger-ui {{ max-width: 1200px; margin: 0 auto; }}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({{
      url: '/openapi.json',
      dom_id: '#swagger-ui',
      presets: [SwaggerUIBundle.presets.apis],
      layout: "BaseLayout"
    }});
  </script>
</body>
</html>"""
    resp = make_response(html, 200)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp
