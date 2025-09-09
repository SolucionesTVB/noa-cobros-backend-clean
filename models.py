from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

class Factura(db.Model):
    __tablename__ = 'facturas'
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String, nullable=False)
    telefono = db.Column(db.String)
    email = db.Column(db.String)
    monto = db.Column(db.Numeric(12,2), nullable=False)
    vence = db.Column(db.Date, nullable=False)
    estado = db.Column(db.String, default='pendiente')  # pendiente | pagada | vencida
    canal = db.Column(db.String, default='whatsapp')    # whatsapp | email | ambos
    ultima_notificacion_at = db.Column(db.DateTime)
    intentos = db.Column(db.SmallInteger, default=0)
    notas = db.Column(db.Text)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

class Plantilla(db.Model):
    __tablename__ = 'plantillas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String, nullable=False)
    canal = db.Column(db.String, nullable=False)             # whatsapp | email
    dias_relativos = db.Column(db.Integer, nullable=False)    # -3, 0, +3
    asunto = db.Column(db.String)
    cuerpo = db.Column(db.Text, nullable=False)

def seed_plantillas(db):
    if db.session.query(Plantilla).count() > 0:
        return
    items = [
        Plantilla(nombre='3_dias_antes', canal='whatsapp', dias_relativos=-3, asunto=None,
                  cuerpo='Hola {{cliente}}, le recordamos su factura por ₡{{monto}} vence el {{vence}}. Responda PAGADO si ya canceló.'),
        Plantilla(nombre='dia_venc', canal='whatsapp', dias_relativos=0, asunto=None,
                  cuerpo='Hola {{cliente}}, hoy vence su factura por ₡{{monto}}. ¿Necesita ayuda para pagar?'),
        Plantilla(nombre='3_dias_despues', canal='whatsapp', dias_relativos=3, asunto=None,
                  cuerpo='Hola {{cliente}}, su factura de ₡{{monto}} venció el {{vence}}. Indíquenos si ya realizó el pago o requiere arreglo.'),
    ]
    db.session.add_all(items)
    db.session.commit()
