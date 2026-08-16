from __future__ import annotations
import asyncio,logging,os,time
from datetime import datetime,timezone,timedelta
import requests
from live_engine import fetch_summary
import score_sync_patch
import ai_signal_journal as journal
import ai_signal_card
from telegram_subscribers import get_subscribers

logger=logging.getLogger('ai_goal_watch')
INTERVAL=max(15,int(os.getenv('AI_GOAL_WATCH_SECONDS','20')))
CONFIRM_MIN=max(30,int(os.getenv('AI_GOAL_CONFIRM_MIN_SECONDS','40')))
CONFIRM_RETRIES=max(1,int(os.getenv('AI_GOAL_CONFIRM_RETRIES','3')))
CONFIRM_RETRY_SECONDS=max(10,int(os.getenv('AI_GOAL_CONFIRM_RETRY_SECONDS','20')))
MSK=timezone(timedelta(hours=3))
_detected={}

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

def _latest_pending_per_event():
 rows=journal.pending();latest={}
 for r in rows:
  eid=str(r.get('event_id') or '')
  if not eid:continue
  old=latest.get(eid)
  if old is None or int(r.get('created_ts',0) or 0)>=int(old.get('created_ts',0) or 0):latest[eid]=r
 for r in rows:
  eid=str(r.get('event_id') or '')
  if eid and latest.get(eid) is not r:
   journal.close(r.get('id'),'void',r.get('final_score'),r.get('goal_minute'))
   logger.warning('AI_OLD_PENDING_VOID event=%s signal=%s',eid,r.get('id'))
 return latest

def _confirm(row,target_score):
 eid=str(row.get('event_id') or '')
 before=_score(row.get('score_at_signal'))
 for attempt in range(CONFIRM_RETRIES):
  if not journal.has_pending_event(eid):return False
  try:
   body=fetch_summary(eid)
   if not body:raise RuntimeError('empty summary')
   current,goal_minute=score_sync_patch._summary_state(body)
   if current is None:raise RuntimeError('no summary score')
   current=tuple(current)
  except Exception as exc:
   logger.warning('AI_GOAL_CONFIRM_FETCH_FAILED %s attempt=%d: %s',eid,attempt+1,exc)
   if attempt+1<CONFIRM_RETRIES:time.sleep(CONFIRM_RETRY_SECONDS);continue
   return False
  if sum(current)<sum(target_score):
   logger.warning('AI_GOAL_CANCELLED %s before=%s candidate=%s current=%s',eid,before,target_score,current)
   return False
  if sum(current)<=sum(before):
   logger.warning('AI_GOAL_ROLLBACK %s before=%s current=%s',eid,before,current)
   return False
  gm=int(goal_minute or 0);entry_min=int(row.get('minute') or 0)
  if gm and gm<=entry_min:
   journal.close(row.get('id'),'void',f'{current[0]}:{current[1]}',goal_minute)
   logger.warning('AI_GOAL_VOID old_or_same_minute event=%s entry=%d goal=%d',eid,entry_min,gm)
   return False
  now=datetime.now(MSK).strftime('%d.%m.%Y %H:%M');new_score=f'{current[0]}:{current[1]}';card=ai_signal_card.render_goal(row,new_score,goal_minute,now)
  if _send(card) and journal.close(row.get('id'),'win',new_score,goal_minute):
   logger.warning('AI_GOAL_CONFIRMED %s %s -> %s',eid,before,current);return True
  return False
 return False

def scan_once():
 found=0;latest=_latest_pending_per_event();now=time.time()
 for eid,r in latest.items():
  try:
   body=fetch_summary(eid)
   if not body:continue
   current,goal_minute=score_sync_patch._summary_state(body)
   if current is None:continue
   before=_score(r.get('score_at_signal'));current=tuple(current)
   if sum(current)<=sum(before):
    _detected.pop(eid,None);continue
   state=_detected.get(eid)
   if state is None or tuple(state.get('target') or ())!=current:
    _detected[eid]={'target':current,'ts':now,'goal_minute':goal_minute}
    logger.warning('AI_GOAL_DETECTED %s %s -> %s | waiting %ss confirmation',eid,before,current,CONFIRM_MIN)
    continue
   if now-float(state.get('ts') or now)<CONFIRM_MIN:continue
   target=tuple(state.get('target') or current);_detected.pop(eid,None)
   if _confirm(r,target):found+=1
  except Exception as exc:logger.info('AI_GOAL_WATCH_FAILED %s: %s',eid,exc)
 return found

async def loop():
 logger.info('AI GOAL WATCH started every %ss | VAR-safe confirmation=%ss x%d',INTERVAL,CONFIRM_MIN,CONFIRM_RETRIES)
 while True:
  await asyncio.to_thread(scan_once);await asyncio.sleep(INTERVAL)
