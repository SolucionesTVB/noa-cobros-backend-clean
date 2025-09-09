import os, csv
from datetime import date
from decimal import Decimal
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models import db, Factura, Plantilla, seed_plantillas
from notify import send_whatsapp
from dotenv import load_dotenv

load_dotenv()

def normalize_db_url(url: str) -> str:
    # SQLAlchemy 2.x prefiere postgresql://
    if url.startswith('postgres://'):
        return 'postgresql://' + url[len('postgres://'):]
    return url

def create_app():
    app = Flask(__name__)
    db_url = normalize_db_url(os.environ['DATABASE_URL'])
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET', 'dev')
    CORS(app, origins=os.environ.get('CORS_ORIGINS','*').split(','))
    Limiter(get_remote_address, app=app, default_limits=[f"{os.getenv('RATE_LIMIT_PER_MINUTE','100')} per minute"]) 
    JWTManager(app)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        seed_plantillas(db)

    @app.get('/health')
    def health():
        return {'ok': True, 'db': 'on', 'status': 'healthy'}

    @app.get('/stats')
    def stats():
        pend = db.session.query(Factura).filter(Factura.estado=='pendiente').count()
        venc = db.session.query(Factura).filter(Factura.estado=='vencida').count()
        return {'pendientes': pend, 'vencidas': venc, 'ok': True}

    @app.get('/facturas')
    def list_facturas():
        q = db.session.query(Factura).order_by(Factura.vence.asc()).all()
        def as_dict(f):
            return {
                'id': f.id,
                'cliente': f.cliente,
                'telefono': f.telefono,
                'email': f.email,
                'monto': float(f.monto),
                'vence': f.vence.isoformat(),
                'estado': f.estado,
                'canal': f.canal,
                'notas': f.notas
            }
        return jsonify([as_dict(f) for f in q])

    @app.post('/facturas')
    def create_factura():
        d = request.get_json(force=True)
        f = Factura(
            cliente=d['cliente'],
            telefono=d.get('telefono'),
            email=d.get('email'),
            monto=Decimal(str(d['monto'])),
            vence=date.fromisoformat(d['vence']),
            estado=d.get('estado','pendiente'),
            canal=d.get('canal','whatsapp'),
            notas=d.get('notas')
        )
        db.session.add(f)
        db.session.commit()
        return {'id': f.id, 'ok': True}

    @app.post('/facturas/import')
    def import_csv():
        if 'file' not in request.files:
            return {'error': 'Falta archivo CSV (campo file)'}, 400
        file = request.files['file']
        reader = csv.DictReader((line.decode('utf-8') for line in file.stream))
        ok, fail = 0, 0
        for row in reader:
            try:
                f = Factura(
                    cliente=row['cliente'].strip(),
                    telefono=row.get('telefono','').strip() or None,
                    email=row.get('email','').strip() or None,
                    monto=Decimal(str(row['monto'])),
                    vence=date.fromisoformat(row['vence'].strip()),
                    canal=(row.get('canal') or 'whatsapp').strip(),
                    notas=row.get('notas')
                )
                db.session.add(f)
                ok += 1
            except Exception:
                fail += 1
        db.session.commit()
        return {'importados': ok, 'fallidos': fail, 'ok': True}

    @app.post('/notificar')
    def notificar():
        data = request.get_json(force=True) or {}
        ids = data.get('ids', [])
        if not ids:
            return {'error': 'Debe enviar ids'}, 400
        enviados = []
        tpl = db.session.query(Plantilla).filter_by(nombre='dia_venc', canal='whatsapp').first()
        for fid in ids:
            f = db.session.get(Factura, fid)
            if not f or not f.telefono:
                continue
            msg = (tpl.cuerpo if tpl else 'Estimado {cliente}, recordatorio de factura por ₡{monto} con fecha {vence}.')                    .replace('{{cliente}}', f.cliente)                    .replace('{{monto}}', f"{float(f.monto):,.0f}")                    .replace('{{vence}}', f.vence.strftime('%d/%m/%Y'))
            try:
                resp = send_whatsapp(f.telefono, msg)
                enviados.append({'id': f.id, 'resp': resp})
            except Exception as e:
                enviados.append({'id': f.id, 'error': str(e)})
        return {'enviados': enviados, 'ok': True}

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))
