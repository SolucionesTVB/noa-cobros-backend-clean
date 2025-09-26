# wsgi.py — entrada para gunicorn (Render)
try:
    from app import app as application
    app = application
except Exception as e:
    raise RuntimeError(f"WSGI import error desde app.py: {e}")
