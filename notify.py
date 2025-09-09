import os, requests

def send_whatsapp(to, text):
    provider = os.getenv('PROVIDER_WHATSAPP','wasender')
    if provider == 'twilio':
        # TODO: Implementar Twilio si se requiere
        raise NotImplementedError('Twilio no implementado en este snippet')
    else:
        base = os.getenv('WASENDER_API_BASE')
        token = os.getenv('WASENDER_API_TOKEN')
        sender = os.getenv('WASENDER_PHONE')
        if not (base and token and sender):
            raise RuntimeError('WASENDER_* vars no configuradas')
        r = requests.post(f"{base}/api/v1/messages", json={
            'token': token,
            'phone': to,
            'message': text,
            'device': sender
        }, timeout=25)
        r.raise_for_status()
        return r.json()
