from __future__ import annotations
import asyncio,logging,os,time
from datetime import datetime,timezone,timedelta
import requests
from live_engine import fetch_summary
import score_sync_patch
import ai_signal_journal as journal
import ai_signal_card
from telegram_subscribers import get_subscribers
logger=logging.getLogger('ai_goal_watch');INTERVAL=max(15,int(os.getenv('AI_GOAL_WATCH_SECONDS','20')));GRACE=max(10,int(os.getenv('AI_GOAL_MIN_VALID_SECONDS','20')));MSK=timezone(timedelta(hours=3))
def _score(s):
 try:a,b=str(s).split(':',1);return int(a),int(b)
 except:return 0,0
def _send(card):
 token=os.getenv('TELEGRAM_BOT_TOKEN','').strip();ok=0
 for cid in get_subscribers():
  try:
   x=requests.post(f'https://api.telegram.org/bot{token}/sendPhoto',data={'chat_id':str(cid)},files={'photo':('gemini_goal_confirmed.png',card,'image/png')},timeout=20)
   if x.ok:ok+=1
   else:logger.warning('AI_GOAL_CARD_SEND_FAILED chat=%s http=%s',cid,x.status_code)
  except requests.RequestException as e:logger.warning('AI_GOAL_CARD_SEND_FAILED %s',e)
 return ok>0
def scan_once():
 found=0
 for r in journal.pending():
  try:
   body=fetch_summary(r.get('event_id'))
   if not body:continue
   current,goal_minute=score_sync_patch._summary_state(body)
   if current is None:continue
   before=_score(r.get('score_at_signal'))
   if sum(current)>sum(before):
    new_score=f'{current[0]}:{current[1]}';entry_min=int(r.get('minute') or 0);age=max(0,int(time.time())-int(r.get('created_ts') or 0));gm=int(goal_minute or 0)
    instant=(age<GRACE) or (gm>0 and gm<=entry_min)
    if instant:
     if journal.close(r.get('id'),'void',new_score,goal_minute):
      logger.warning('AI_GOAL_VOID instant_goal event=%s entry=%d goal=%s age=%ss %s->%s',r.get('event_id'),entry_min,goal_minute,age,before,current)
     continue
    now=datetime.now(MSK).strftime('%d.%m.%Y %H:%M');card=ai_signal_card.render_goal(r,new_score,goal_minute,now)
    if _send(card) and journal.close(r.get('id'),'win',new_score,goal_minute):
     logger.warning('AI_GOAL_CONFIRMED %s %s -> %s',r.get('event_id'),before,current);found+=1
  except Exception as exc:logger.info('AI_GOAL_WATCH_FAILED %s: %s',r.get('event_id'),exc)
 return found
async def loop():
 logger.info('AI GOAL WATCH started every %ss | valid-goal grace=%ss',INTERVAL,GRACE)
 while True:
  await asyncio.to_thread(scan_once);await asyncio.sleep(INTERVAL)
