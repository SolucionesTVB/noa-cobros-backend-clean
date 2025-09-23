from datetime import datetime
from app import db

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, index=True, nullable=False)
    # Guardamos SIEMPRE hash de la contraseña aquí:
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), default="client", index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # === tenants (multi-tenant) ===
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy import Enum as PgEnum

class OrgRoleEnum(db.Enum):
    pass

try:
    from enum import Enum
    class OrgRole(Enum):
        owner = "owner"
        manager = "manager"
        agent = "agent"
        viewer = "viewer"
        suspended = "suspended"
except Exception:
    # fallback simple si no tienes enum
    OrgRole = type("OrgRole", (), {"owner":"owner","manager":"manager","agent":"agent","viewer":"viewer","suspended":"suspended"})

class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(80), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

class OrgMembership(db.Model):
    __tablename__ = "org_memberships"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id  = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role    = db.Column(db.String(20), nullable=False)  # guardamos texto del rol
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    # Opcional: relaciones si quieres
    # user = db.relationship("User")
    # org  = db.relationship("Organization")
# --- MULTI-TENANT: organizations + org_memberships ---
import uuid
from sqlalchemy import String, DateTime
from sqlalchemy.sql import func

class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(80), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

class OrgMembership(db.Model):
    __tablename__ = "org_memberships"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # ajusta tipo si tu users.id no es Integer
    org_id  = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role    = db.Column(db.String(20), nullable=False)  # owner/manager/agent/viewer/suspended
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

