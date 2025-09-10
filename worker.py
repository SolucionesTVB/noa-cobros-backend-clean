# worker.py — Envío automático T-15, T-7 y T-0 con pausa anti-429
# Acepta horario como:
#   - CRON_TIME="2:11"  (recomendado)
#   - o CRON_HOUR="2" y CRON_MINUTE="11"
#
# ENV útiles:
#   BACKEND_URL=https://noa-cobros-backend-clean.onrender.com
#   WAVE_DAYS=15,7,0
#   PAUSE_SEC=12
#   TZ=America/Costa_Rica
#   CRON_TIME=8:00   (o CRON_HOUR=8 / CRON_MINUTE=0)
#   RUN_ON_START=0/1 (si 1, ejecuta inmediatamente al arrancar)
#   DRY_RUN=0/1      (si 1, solo imprime, no envía)

import os
import time
import json
import requests
import datetime as dt
from apscheduler.schedulers.blocking import BlockingScheduler

# -------- Config --------
BACKEND = os.getenv("BACKEND_URL", "https://noa-cobros-backend-clean.onrender.com").rstrip("/")
WAVES   = [int(x) for x in os.getenv("WAVE_DAYS", "15,7,0").replace(" ", "").split(",") if x]
PAUSE   = int(os.getenv("PAUSE_SEC", "12"))
TZ      = os.getenv("TZ", "America/Costa_Rica")
RUN_ON_START = os.getenv("RUN_ON_START", "0") == "1"
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

def _parse_schedule():
    """Devuelve (hour, minute) aceptando CRON_TIME='HH:MM' o H/M separados."""
    ct = os.getenv("CRON_TIME")
    if ct and ":" in ct:
        h, m = ct.split(":", 1)
        return int(h.strip()), int(m.strip())
    ch = os.getenv("CRON_HOUR", "8")
    cm = os.getenv("CRON_MINUTE", "0")
    if ":" in ch:  # por si pusieron '2:11' en CRON_HOUR
        h, m = ch.split(":", 1)
        return int(h.strip()), int(m.strip())
    return int(ch), int(cm)

HOUR, MINUTE = _parse_schedule()

# -------- Helpers --------
def _get_facturas():
    r = requests.get(f"{BACKEND}/facturas", timeout=40)
    r.raise_for_status()
    # Debe ser una lista de dicts
    return r.json()

def _days_to(date_str):
    try:
        vence = dt.date.fromisoformat(str(date_str)[:10])
        hoy   = dt.date.today()
        return (vence - hoy).days
    except Exception:
        return None

def _post_notificar(ids):
    """POST /notificar con lista de ids. Devuelve (ok, payload/text)."""
    url = f"{BACKEND}/notificar"
    if DRY_RUN:
        return True, {"dry_run": True, "ids": ids}
    r = requests.post(url, json={"ids": ids}, timeout=60)
    ctype = r.headers.get("content-type", "")
    payload = r.json() if "application/json" in ctype else r.text
    ok = r.ok
    return ok, payload

def _contains_429(payload):
    s = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return "Too Many Requests" in s or "429" in s

def _send_ids_slow(ids, pause_sec):
    """Envía de a 1 id con pausa; si detecta 429, espera 60s y reintenta 1 vez."""
    enviados = []
    for i in ids:
        ok, payload = _post_notificar([i])
        if not ok and _contains_429(payload):
            # espera y reintenta una vez
            time.sleep(60)
            ok2, payload2 = _post_notificar([i])
            enviados.append({"id": i, "ok": ok2, "resp": payload2})
        else:
            enviados.append({"id": i, "ok": ok, "resp": payload})
        time.sleep(pause_sec)
    return enviados

# -------- Job principal --------
def run_job():
    now = dt.datetime.now()
    print(f"[{now}] Runner inicia. BACKEND={BACKEND} WAVES={WAVES} PAUSE={PAUSE}s DRY_RUN={DRY_RUN}")
    try:
        data = _get_facturas()
    except Exception as e:
        print(f"[{dt.datetime.now()}] ERROR al leer /facturas: {e}")
        return

    # Construir buckets por días restantes
    por_wave = {w: [] for w in WAVES}
    for row in data if isinstance(data, list) else []:
        dleft = _days_to(row.get("vence", ""))
        if dleft in por_wave:
            rid = row.get("id")
            if isinstance(rid, int):
                por_wave[dleft].append(rid)

    total = 0
    for w in WAVES:
        ids = por_wave.get(w, [])
        print(f"[{dt.datetime.now()}] Wave T-{w}: {len(ids)} IDs")
        if not ids:
            continue
        enviados = _send_ids_slow(ids, PAUSE)
        total += len(ids)
        # Resumen corto
        oks = sum(1 for x in enviados if x.get("ok"))
        print(f"[{dt.datetime.now()}] Wave T-{w} enviado(s): {oks}/{len(ids)}")
    print(f"[{dt.datetime.now()}] Runner fin. Total IDs enviados: {total}")

# -------- Scheduler --------
if __name__ == "__main__":
    print(f"Scheduler en zona {TZ}. Programado a las {HOUR:02d}:{MINUTE:02d} todos los días.")
    sch = BlockingScheduler(timezone=TZ)
    sch.add_job(run_job, "cron", hour=HOUR, minute=MINUTE)
    if RUN_ON_START:
        # Ejecuta una vez al arrancar (útil para probar)
        run_job()
    try:
        sch.start()
    except (KeyboardInterrupt, SystemExit):
        pass
