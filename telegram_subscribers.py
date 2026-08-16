from __future__ import annotations
import asyncio,json,logging,os
from pathlib import Path
import requests
import ai_signal_journal as journal
logger=logging.getLogger('telegram_subscribers')
FILE=Path('ai_telegram_subscribers.json')
def _token():return os.getenv('TELEGRAM_BOT_TOKEN','').strip()
def _owner():return os.getenv('TELEGRAM_CHAT_ID','').strip()
def _read():
 try:x=json.loads(FILE.read_text('utf-8'));return {str(v) for v in x} if isinstance(x,list) else set()
 except:return set()
def _write(s):FILE.write_text(json.dumps(sorted(s),ensure_ascii=False),'utf-8')
def get_subscribers():
 s=_read();
 if _owner():s.add(_owner())
 return sorted(s)
def subscribe(cid):s=_read();s.add(str(cid));_write(s)
def unsubscribe(cid):s=_read();s.discard(str(cid));_write(s)
def _send(cid,text,kb=True):
 p={'chat_id':str(cid),'text':text,'parse_mode':'HTML','disable_web_page_preview':True}
 if kb:p['reply_markup']={'keyboard':[[{'text':'📊 Отчёт'},{'text':'🟢 В игре'}]],'resize_keyboard':True}
 try:return requests.post(f"https://api.telegram.org/bot{_token()}/sendMessage",json=p,timeout=15).ok
 except:return False
def _handle(m):
 cid=(m.get('chat') or {}).get('id');text=str(m.get('text') or '').strip();cmd=text.split(maxsplit=1)[0].lower() if text else ''
 if cid is None:return
 if cmd in {'/start','/menu'}:subscribe(cid);_send(cid,'✅ <b>GEMINI LIVE SCOUT подключён</b>\n\nЯ независимо анализирую LIVE-данные Flashscore и ищу ещё один гол.\n/report — отчёт\n/live — сигналы в игре')
 elif cmd=='/report' or text.casefold()=='📊 отчёт':_send(cid,journal.build_report())
 elif cmd=='/live' or text.casefold() in {'🟢 в игре','в игре'}:
  rows=journal.pending();lines=[f"🟢 <b>В ИГРЕ — {len(rows)}</b>",""]
  for r in rows[-15:][::-1]:lines.append(f"⏳ <b>{r.get('home')} — {r.get('away')}</b>\n↳ {r.get('minute')}' · {r.get('score_at_signal')} · AI {r.get('probability')}%")
  _send(cid,'\n'.join(lines))
 elif cmd=='/stop' and str(cid)!=_owner():unsubscribe(cid);_send(cid,'🔕 Рассылка отключена.')
def _poll(offset):
 try:
  p={'timeout':25,'allowed_updates':json.dumps(['message'])};
  if offset is not None:p['offset']=offset
  r=requests.get(f"https://api.telegram.org/bot{_token()}/getUpdates",params=p,timeout=35)
  if not r.ok:return offset
  for u in r.json().get('result',[]):
   if isinstance(u.get('update_id'),int):offset=u['update_id']+1
   if isinstance(u.get('message'),dict):_handle(u['message'])
 except Exception as e:logger.warning('AI telegram polling failed: %s',e)
 return offset
async def polling_loop():
 off=None;logger.info('AI Telegram polling started')
 while True:off=await asyncio.to_thread(_poll,off);await asyncio.sleep(.5)
