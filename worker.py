import os
from datetime import date, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from models import db, Factura, Plantilla
from notify import send_whatsapp
from app import create_app

app = create_app()

H_BEFORE = int(os.getenv('NOTIFY_DAYS_BEFORE', '3'))
H_AFTER  = int(os.getenv('NOTIFY_DAYS_AFTER', '3'))

sched = BlockingScheduler(timezone=os.getenv('TZ','America/Costa_Rica'))

@sched.scheduled_job('cron', hour=int(os.getenv('CRON_HOUR','8')), minute=0)
def daily_notifications():
    with app.app_context():
        today = date.today()
        due_soon = Factura.query.filter(Factura.vence==today + timedelta(days=H_BEFORE)).all()
        due_today = Factura.query.filter(Factura.vence==today).all()
        overdue  = Factura.query.filter(Factura.vence==today - timedelta(days=H_AFTER), Factura.estado=='pendiente').all()

        for group, tname in [(due_soon,'3_dias_antes'), (due_today,'dia_venc'), (overdue,'3_dias_despues')]:
            tpl = Plantilla.query.filter_by(nombre=tname, canal='whatsapp').first()
            if not tpl: 
                continue
            for f in group:
                if not f.telefono:
                    continue
                msg = tpl.cuerpo.replace('{{cliente}}', f.cliente)                                .replace('{{monto}}', f"{float(f.monto):,.0f}")                                .replace('{{vence}}', f.vence.strftime('%d/%m/%Y'))
                try:
                    send_whatsapp(f.telefono, msg)
                except Exception:
                    pass

if __name__ == '__main__':
    sched.start()
