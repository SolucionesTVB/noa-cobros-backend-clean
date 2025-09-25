# wsgi.py — entrada para gunicorn (Render)
try:
    from app import app as application  # gunicorn usa "application"
    app = application # alias por si usan wsgi:app
except Exception as e:
    raise RuntimeError(f"WSGI import error desde app.py: {e}")
