# wsgi.py — entrada única para gunicorn en Render
# Asegura que se importe la Flask app desde app.py
try:
    from app import app as application  # gunicorn usa "application"
    app = application                   # alias por si se usa "wsgi:app"
except Exception as e:
    # fallback con mensaje claro
    raise RuntimeError(f"WSGI import error desde app.py: {e}")
