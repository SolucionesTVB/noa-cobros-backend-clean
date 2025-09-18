# === JWT + rutas de auth (añadido) ===
from flask_jwt_extended import JWTManager
import os as _os
try:
    app.config["JWT_SECRET_KEY"] = _os.getenv("JWT_SECRET_KEY", 
"noa_jwt_2025_super")
except NameError:
    pass
jwt = JWTManager(app)

from auth import bp as auth_bp
app.register_blueprint(auth_bp)
# === /fin añadido ===
# === JWT + rutas de auth (añadido) ===
from flask_jwt_extended import JWTManager
import os as _os
try:
    app.config["JWT_SECRET_KEY"] = _os.getenv("JWT_SECRET_KEY", 
"noa_jwt_2025_super")
except NameError:
    pass
jwt = JWTManager(app)

from auth import bp as auth_bp
app.register_blueprint(auth_bp)
# === /fin añadido ===


