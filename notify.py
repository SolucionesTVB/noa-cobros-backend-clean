import os, requests

def send_whatsapp(to, text):
    base = os.getenv('WASENDER_API_BASE', 'https://www.wasenderapi.com')
    api_key = os.getenv('WASENDER_API_TOKEN') or os.getenv('WASENDER_API_KEY')
    if not api_key:
        raise RuntimeError('Falta WASENDER_API_TOKEN o WASENDER_API_KEY')
    url = f"{base.rstrip('/')}/api/send-message"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {'to': to, 'text': text}
    r = requests.post(url, json=payload, headers=headers, timeout=25)
    r.raise_for_status()
    return r.json()
