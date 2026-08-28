import requests


def send(token, chat_id, text):
    if not token or not chat_id: return False
    r=requests.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat_id,'text':text,'parse_mode':'HTML','disable_web_page_preview':True},timeout=15)
    return r.ok
