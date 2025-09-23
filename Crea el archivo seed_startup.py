# seed_startup.py
import os
from models import db, User  # ajusta si tu modelo se llama distinto

def _get_user_by_username(username):
    return User.query.filter_by(username=username).first()

def _get_user_by_email(email):
    return User.query.filter_by(email=email).first() if hasattr(User, "email") else None

def _set_password(u, raw):
    # werkzeug hash si lo usas
    try:
        from werkzeug.security import generate_password_hash
        hashed = generate_password_hash(raw)
    except:
        hashed = raw  # Fallback (no recomendado)
    if hasattr(u, "password_hash"):
        u.password_hash = hashed
    elif hasattr(u, "password"):
        u.password = hashed

def _ensure_user(username, email, password, is_admin=False):
    u = _get_user_by_username(username) or (email and _get_user_by_email(email))
    if not u:
        kwargs = dict(username=username)
        if hasattr(User, "email"): kwargs["email"] = email
        if hasattr(User, "is_active"): kwargs["is_active"] = True
        if hasattr(User, "is_admin"):  kwargs["is_admin"]  = is_admin
        # set password
        try:
            from werkzeug.security import generate_password_hash
            kwargs["password_hash" if hasattr(User, "password_hash") else "password"] = generate_password_hash(password)
        except:
            kwargs["password_hash" if hasattr(User, "password_hash") else "password"] = password
        u = User(**kwargs)
        db.session.add(u)
        db.session.commit()
    else:
        _set_password(u, password)
        db.session.commit()
    return u

def seed_startup():
    # crea tablas existentes en models.py (si usas db.create_all)
    try:
        db.create_all()
    except Exception as e:
        print("[seed] create_all warning:", e)

    admin_user = os.getenv("ADMIN_USERNAME", "tony")
    admin_email = os.getenv("ADMIN_EMAIL", "vtonyb@gmail.com")
    admin_pass  = os.getenv("ADMIN_PASSWORD", "Noa2025!")

    _ensure_user(admin_user, admin_email, admin_pass, True)
    _ensure_user("jeff",    "jeff@noa.seg",    "Noa2025!", False)
    _ensure_user("hermann", "hermann@noa.seg", "Noa2025!", False)
    print("[startup] seed OK")
