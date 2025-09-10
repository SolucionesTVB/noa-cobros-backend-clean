# worker.py — envía avisos T-15, T-7 y T-0 cada día
import os, time, requests, datetime as dt
from apscheduler.schedulers.blocking import BlockingScheduler

BACKEND = os.getenv("BACKEND_URL","https://noa-cobros-backend-clean.onrender.com").rstrip("/")
WAVES   = [int(x) for x in os.getenv("WAVE_DAYS","15,7,0").split(",") if x.strip()]
PAUSE   = int(os.getenv("PAUSE_SEC","12"))
TZ      = os.getenv("TZ","America/Costa_Rica")
HOUR    = int(os.getenv("CRON_HOUR","8"))

def _get_facturas():
    r = requests.get(f"{BACKEND}/facturas", timeout=30)
    r.raise_for_status()
    return r.json()

def _days_to(date_str):
    try:
        vence = dt.date.fromisoformat(date_str[:10])
        hoy   = dt.date.today()
        return (vence - hoy).days
    except Exception:
        return None

def _send_ids(ids):
    if not ids: return {"ok": True, "enviados": []}
    enviados = []
    for i in ids:
        try:
            r = requests.post(f"{BACKEND}/notificar", json={"ids":[i]}, timeout=40)
            if r.headers.get("content-type","").startswith("application/json"):
                enviados.append({"id": i, "resp": r.json()})
            else:
                enviados.append({"id": i, "resp": r.text})
        except Exception as e:
            enviados.append({"id": i, "error": str(e)})
        time.sleep(PAUSE)  # pausa anti-429
    return {"ok": True, "enviados": enviados}

def run_job():
    print(f"[{dt.datetime.now()}] Runner inicia. Waves={WAVES}")
    data = _get_facturas()
    por_wave = {w: [] for w in WAVES}
    for row in data:
        d = _days_to(str(row.get("vence","")))
        if d in por_wave:
            por_wave[d].append(row["id"])
    total = 0
    for w in WAVES:
        ids = por_wave[w]
        if not ids:
            print(f"Wave T-{w}: 0 IDs")
            continue
        print(f"Wave T-{w}: {len(ids)} IDs → enviar")
        resp = _send_ids(ids)
        total += len(ids)
        print(resp)
    print(f"[{dt.datetime.now()}] Runner fin. Enviados: {total}")

if __name__ == "__main__":
    sch = BlockingScheduler(timezone=TZ)
    sch.add_job(run_job, "cron", hour=HOUR, minute=0)
    print(f"Worker listo. Ejecutará a las {HOUR}:00 ({TZ}) cada día.")
    try:
        sch.start()
    except (KeyboardInterrupt, SystemExit):
        pass
