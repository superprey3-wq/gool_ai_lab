"""Independent Gemini LIVE scout: production GOOL live-state flow + Gemini decision."""
from __future__ import annotations
import asyncio,copy,json,logging,os,time
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
from live_engine import fetch_stats,parse_stats
import unified_bot
import ai_signal_journal as journal
import ai_signal_card
from telegram_subscribers import get_subscribers

logger=logging.getLogger("gemini_live_scout")
MODELS=[x.strip() for x in os.getenv("GEMINI_MODELS","gemini-3.6-flash,gemini-3.5-flash-lite,gemini-3.5-flash").split(",") if x.strip()]
KEY=os.getenv("GEMINI_API_KEY","").strip()
MINUTE_MIN=int(os.getenv("GEMINI_SCOUT_MINUTE","10"));MINUTE_MAX=int(os.getenv("GEMINI_SCOUT_MAX_MINUTE","88"));ENTER_PROB=int(os.getenv("GEMINI_SCOUT_ENTER_PROB","70"));WORKERS=max(2,int(os.getenv("GEMINI_SCOUT_WORKERS","4")));RECHECK=max(120,int(os.getenv("GEMINI_SCOUT_RECHECK_SECONDS","240")));MAX_AI_PER_CYCLE=max(1,int(os.getenv("GEMINI_SCOUT_MAX_AI_PER_CYCLE","8")));MAX_SIGNAL_DRIFT=max(1,int(os.getenv("GEMINI_SCOUT_MAX_SIGNAL_DRIFT","2")))
ENTRY_REFRESH_RETRIES=max(1,int(os.getenv("GEMINI_ENTRY_REFRESH_RETRIES","2")));ENTRY_REFRESH_RETRY_SECONDS=max(1,int(os.getenv("GEMINI_ENTRY_REFRESH_RETRY_SECONDS","2")))
MOSCOW_TZ=timezone(timedelta(hours=3));_seen={}
SCHEMA={"type":"OBJECT","properties":{"decision":{"type":"STRING","enum":["ENTER","WATCH","REJECT","NO_DATA"]},"goal_probability":{"type":"INTEGER","minimum":1,"maximum":99},"horizon_minutes":{"type":"INTEGER","minimum":1,"maximum":30},"confidence":{"type":"STRING","enum":["LOW","MEDIUM","HIGH"]},"reason":{"type":"STRING"},"risk":{"type":"STRING"}},"required":["decision","goal_probability","horizon_minutes","confidence","reason","risk"]}

def pair(s,k):
 try:a,b=s.get(k,(0,0));return [float(a or 0),float(b or 0)]
 except:return [0,0]
def useful(s):return sum(sum(pair(s,k)) for k in ("xg","shots","shots_on_target","big_chances","corners","shots_inside_box","touches_box"))>0

def prompt(p):
 return """Ты независимый профессиональный футбольный LIVE-аналитик. Твоя специализация — ловить ЕЩЁ ОДИН ГОЛ в текущем матче. Анализируй ТОЛЬКО предоставленный актуальный снимок LIVE-данных Flashscore. minute и score в DATA — единственные истинные текущие минута и счёт. НИКОГДА не утверждай, что команда уже забила гол, если это не отражено в score. История голов специально не передаётся: не выдумывай минуты или предыдущие голы. horizon_minutes считай вперёд от DATA.minute. Учитывай турнир, xG, удары, удары в створ, big chances, действия в штрафной и угловые. ENTER — только когда сам видишь убедительное основание ждать минимум один следующий гол. WATCH — потенциал есть, но рано. REJECT — гол недостаточно вероятен. NO_DATA — данных мало. Поля reason и risk пиши только на русском. В reason начинай: «Сейчас N-я минута, счёт X:Y». Не выдумывай события. Верни только JSON по схеме.\nDATA:\n"""+json.dumps(p,ensure_ascii=False)

def ask(p):
 if not KEY:return None,"missing_api_key",None
 body={"contents":[{"role":"user","parts":[{"text":prompt(p)}]}],"generationConfig":{"maxOutputTokens":300,"response_mime_type":"application/json","response_schema":SCHEMA}};last=""
 for model in MODELS:
  try:r=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",headers={"x-goog-api-key":KEY,"Content-Type":"application/json"},json=body,timeout=18)
  except requests.RequestException as e:last=f"request:{e}";continue
  if not r.ok:last=f"{model}:http{r.status_code}";continue
  try:
   txt="".join(str(x.get("text") or "") for x in r.json()["candidates"][0]["content"]["parts"] if isinstance(x,dict));return json.loads(txt),None,model
  except Exception:last=f"{model}:bad_json"
 return None,last,None

def fetch_one(m):
 try:raw=fetch_stats(m.event_id);return m,parse_stats(raw) if raw else {}
 except:return m,{}

def payload(m,s):
 return {"event_id":str(m.event_id),"home":m.home,"away":m.away,"league":getattr(m,"league","") or "турнир не определён","minute":int(m.minute or 0),"score":[int(m.home_score or 0),int(m.away_score or 0)],"xg":pair(s,"xg"),"shots":pair(s,"shots"),"shots_on_target":pair(s,"shots_on_target"),"big_chances":pair(s,"big_chances"),"corners":pair(s,"corners"),"shots_inside_box":pair(s,"shots_inside_box"),"touches_box":pair(s,"touches_box"),"snapshot_time_msk":datetime.now(MOSCOW_TZ).strftime("%H:%M:%S")}

def _send_photo(card):
 token=os.getenv("TELEGRAM_BOT_TOKEN","").strip();ok=0
 for cid in get_subscribers():
  try:
   r=requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",data={"chat_id":str(cid)},files={"photo":("gemini_live_scout.png",card,"image/png")},timeout=20)
   if r.ok:ok+=1
   else:logger.warning("GEMINI_CARD_SEND_FAILED chat=%s http=%s %s",cid,r.status_code,r.text[:160])
  except requests.RequestException as e:logger.warning("GEMINI_CARD_SEND_FAILED chat=%s %s",cid,e)
 return ok>0

def _fresh_live_match(event_id):
 """Same principle as production GOOL: fresh LIVE list is authoritative for entry minute/score."""
 for attempt in range(ENTRY_REFRESH_RETRIES):
  try:
   live=asyncio.run(unified_bot.discover_live_matches())
   found=next((x for x in live if str(getattr(x,'event_id',''))==str(event_id)),None)
   if found is not None:return found
  except Exception as exc:logger.warning("GEMINI_LIVE_REFRESH_FAILED %s attempt=%d: %s",event_id,attempt+1,exc)
  if attempt+1<ENTRY_REFRESH_RETRIES:time.sleep(ENTRY_REFRESH_RETRY_SECONDS)
 return None

def _sync_entry_match(m):
 fresh=_fresh_live_match(m.event_id)
 if fresh is None:
  logger.warning("GEMINI_ENTRY_SKIPPED_NO_FRESH_LIVE %s",m.event_id);return None
 synced=copy.copy(m);synced.minute=int(getattr(fresh,'minute',0) or 0);synced.home_score=int(getattr(fresh,'home_score',0) or 0);synced.away_score=int(getattr(fresh,'away_score',0) or 0);synced.is_halftime=bool(getattr(fresh,'is_halftime',False))
 logger.info("GEMINI_ENTRY_SYNCED %s score=%d:%d minute=%d",m.event_id,synced.home_score,synced.away_score,synced.minute);return synced

def send(m,v,model):
 if journal.has_pending_event(m.event_id):logger.warning("GEMINI_DUPLICATE_BLOCKED %s reason=pending_signal",m.event_id);return False
 # Production GOOL refreshes again immediately before rendering/sending an entry card.
 fresh=_sync_entry_match(m)
 if fresh is None:return False
 expected=(int(m.home_score or 0),int(m.away_score or 0));actual=(int(fresh.home_score or 0),int(fresh.away_score or 0))
 if actual!=expected or abs(int(fresh.minute or 0)-int(m.minute or 0))>MAX_SIGNAL_DRIFT:
  logger.warning("GEMINI_ENTRY_CHANGED_BEFORE_SEND %s old=%s %s' fresh=%s %s'",m.event_id,expected,m.minute,actual,fresh.minute);return False
 if int(fresh.minute or 0)>MINUTE_MAX:return False
 prob=int(v.get("goal_probability") or 0);h=int(v.get("horizon_minutes") or 0);league=getattr(fresh,"league","") or getattr(m,"league","") or "турнир не определён";now_msk=datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M")
 try:card=ai_signal_card.render(fresh,v,model,now_msk)
 except Exception:logger.exception("GEMINI_CARD_RENDER_FAILED %s",m.event_id);return False
 # One final LIVE refresh after rendering: score must still be exactly the score Gemini analysed.
 final=_fresh_live_match(m.event_id)
 if final is None:return False
 final_score=(int(final.home_score or 0),int(final.away_score or 0))
 if final_score!=actual or int(final.minute or 0)>MINUTE_MAX:
  logger.warning("GEMINI_ENTRY_ABORTED_LAST_SECOND %s card=%s final=%s",m.event_id,actual,final_score);return False
 if not _send_photo(card):return False
 journal.add({"event_id":str(m.event_id),"home":fresh.home,"away":fresh.away,"league":league,"minute":int(fresh.minute or 0),"score_at_signal":f"{actual[0]}:{actual[1]}","probability":prob,"horizon":h,"confidence":v.get('confidence',''),"model":model,"reason":v.get('reason',''),"risk":v.get('risk','')});return True

def _freshen_before_send(m,v,model):
 fresh=_sync_entry_match(m)
 if not fresh:return None,None,None
 old_min=int(getattr(m,'minute',0) or 0);new_min=int(getattr(fresh,'minute',0) or 0);old_score=(int(getattr(m,'home_score',0) or 0),int(getattr(m,'away_score',0) or 0));new_score=(int(getattr(fresh,'home_score',0) or 0),int(getattr(fresh,'away_score',0) or 0))
 if new_min>MINUTE_MAX:return None,None,None
 drift=max(0,new_min-old_min);changed=drift>MAX_SIGNAL_DRIFT or new_score!=old_score
 if not changed:return fresh,v,model
 logger.warning("GEMINI_REANALYZE_FRESH %s old=%d %s new=%d %s",m.event_id,old_min,old_score,new_min,new_score)
 try:raw=fetch_stats(fresh.event_id);s=parse_stats(raw) if raw else {}
 except:s={}
 if not useful(s):return None,None,None
 nv,e,nmodel=ask(payload(fresh,s))
 if not nv:logger.warning("GEMINI_FRESH_AI_FAILED %s %s",m.event_id,e);return None,None,None
 if str(nv.get('decision') or '')!='ENTER' or int(nv.get('goal_probability') or 0)<ENTER_PROB:logger.warning("GEMINI_FRESH_REJECT %s %d' %s %s%%",m.event_id,new_min,nv.get('decision'),nv.get('goal_probability'));return None,None,None
 return fresh,nv,nmodel

def scan(live):
 now=time.time();c=[]
 for m in live:
  minute=int(getattr(m,"minute",0) or 0)
  if minute<MINUTE_MIN or minute>MINUTE_MAX or getattr(m,"is_halftime",False):continue
  if journal.has_pending_event(m.event_id):logger.info("GEMINI_SKIP_ACTIVE %s",m.event_id);continue
  old=_seen.get(str(m.event_id));score=(int(m.home_score or 0),int(m.away_score or 0))
  if old and now-old[0]<RECHECK and old[1]==score:continue
  c.append(m)
 stats={}
 if c:
  with ThreadPoolExecutor(max_workers=min(WORKERS,len(c))) as ex:
   for f in as_completed([ex.submit(fetch_one,m) for m in c]):m,s=f.result();stats[str(m.event_id)]=s
 def activity(m):
  s=stats.get(str(m.event_id),{});return sum(pair(s,"shots_on_target"))*5+sum(pair(s,"big_chances"))*6+sum(pair(s,"xg"))*4+sum(pair(s,"shots"))*.5
 ready=[m for m in c if useful(stats.get(str(m.event_id),{}))];ready.sort(key=activity,reverse=True);sent=checked=0
 for m in ready[:MAX_AI_PER_CYCLE]:
  if journal.has_pending_event(m.event_id):continue
  s=stats[str(m.event_id)];v,e,model=ask(payload(m,s));checked+=1;_seen[str(m.event_id)]=(now,(int(m.home_score or 0),int(m.away_score or 0)))
  if not v:logger.warning("GEMINI_SCOUT_FAILED %s %s",m.event_id,e);continue
  d=str(v.get("decision") or "");prob=int(v.get("goal_probability") or 0);logger.warning("GEMINI_SCOUT %d' %s — %s %d:%d | %s %d%% | model=%s",m.minute,m.home,m.away,m.home_score,m.away_score,d,prob,model)
  if d=="ENTER" and prob>=ENTER_PROB:
   fm,fv,fmodel=_freshen_before_send(m,v,model)
   if fm is not None and not journal.has_pending_event(fm.event_id) and send(fm,fv,fmodel):sent+=1
 logger.info("GEMINI_SCOUT_CYCLE live=%d data_candidates=%d ai_checked=%d sent=%d",len(live),len(ready),checked,sent);return sent
