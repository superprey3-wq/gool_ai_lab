"""Independent Gemini LIVE scout: raw Flashscore-derived stats -> Gemini -> Telegram."""
from __future__ import annotations
import json,logging,os,time
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
from live_engine import fetch_stats,parse_stats,fetch_summary,parse_goal_timeline
import unified_bot
logger=logging.getLogger("gemini_live_scout")
MODELS=[x.strip() for x in os.getenv("GEMINI_MODELS","gemini-3.6-flash,gemini-3.5-flash-lite,gemini-3.5-flash").split(",") if x.strip()]
KEY=os.getenv("GEMINI_API_KEY","").strip()
MINUTE_MIN=int(os.getenv("GEMINI_SCOUT_MINUTE","10"));MINUTE_MAX=int(os.getenv("GEMINI_SCOUT_MAX_MINUTE","88"));ENTER_PROB=int(os.getenv("GEMINI_SCOUT_ENTER_PROB","70"));WORKERS=max(2,int(os.getenv("GEMINI_SCOUT_WORKERS","4")));RECHECK=max(120,int(os.getenv("GEMINI_SCOUT_RECHECK_SECONDS","240")));MAX_AI_PER_CYCLE=max(1,int(os.getenv("GEMINI_SCOUT_MAX_AI_PER_CYCLE","8")))
MOSCOW_TZ=timezone(timedelta(hours=3))
_seen={}
SCHEMA={"type":"OBJECT","properties":{"decision":{"type":"STRING","enum":["ENTER","WATCH","REJECT","NO_DATA"]},"goal_probability":{"type":"INTEGER","minimum":1,"maximum":99},"horizon_minutes":{"type":"INTEGER","minimum":1,"maximum":30},"confidence":{"type":"STRING","enum":["LOW","MEDIUM","HIGH"]},"reason":{"type":"STRING"},"risk":{"type":"STRING"}},"required":["decision","goal_probability","horizon_minutes","confidence","reason","risk"]}
def pair(s,k):
 try:a,b=s.get(k,(0,0));return [float(a or 0),float(b or 0)]
 except:return [0,0]
def useful(s):
 return sum(sum(pair(s,k)) for k in ("xg","shots","shots_on_target","big_chances","corners","shots_inside_box","touches_box"))>0
def prompt(p):
 return """Ты независимый профессиональный футбольный LIVE-аналитик. Твоя специализация — ловить ЕЩЁ ОДИН ГОЛ в текущем матче (рынок тотал больше от текущего счёта). Ты не знаешь решений GOOL, MASTER, MATH или других моделей. Анализируй ТОЛЬКО предоставленные сырые LIVE-данные Flashscore: названия команд, турнир/лигу, минуту, счёт, xG, удары, удары в створ, big chances, действия/касания в штрафной, угловые и уже забитые голы. Учитывай контекст турнира только если он явно указан в DATA; ничего не выдумывай. Оцени характер счёта, мотивацию атаковать, темп и оставшееся время. ENTER — только когда сам видишь убедительное основание ждать минимум один следующий гол. WATCH — потенциал есть, но сейчас рано. REJECT — гол недостаточно вероятен. NO_DATA — данных мало. Не выдумывай отсутствующие показатели.
ВАЖНО: поля reason и risk пиши ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, естественно и кратко. Никогда не используй английские предложения в reason или risk. В reasoning можешь явно ссылаться на команды и турнир из DATA. Названия команд и турнира оставляй как они пришли из Flashscore. reason — 1-2 главных аргумента. risk — один главный риск. goal_probability — честная вероятность хотя бы одного следующего гола до конца матча. horizon_minutes — наиболее вероятный горизонт следующего гола. Верни только JSON по схеме.\nDATA:\n"""+json.dumps(p,ensure_ascii=False)
def ask(p):
 if not KEY:return None,"missing_api_key",None
 body={"contents":[{"role":"user","parts":[{"text":prompt(p)}]}],"generationConfig":{"maxOutputTokens":300,"response_mime_type":"application/json","response_schema":SCHEMA}}
 last=""
 for model in MODELS:
  try:r=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",headers={"x-goog-api-key":KEY,"Content-Type":"application/json"},json=body,timeout=18)
  except requests.RequestException as e:last=f"request:{e}";continue
  if not r.ok:last=f"{model}:http{r.status_code}";continue
  try:
   txt="".join(str(x.get("text") or "") for x in r.json()["candidates"][0]["content"]["parts"] if isinstance(x,dict));return json.loads(txt),None,model
  except Exception:last=f"{model}:bad_json"
 return None,last,None
def fetch_one(m):
 try:
  raw=fetch_stats(m.event_id);return m,parse_stats(raw) if raw else {}
 except:return m,{}
def goals(m):
 try:
  raw=fetch_summary(m.event_id);return parse_goal_timeline(raw) if raw else []
 except:return []
def payload(m,s):
 return {"event_id":str(m.event_id),"home":m.home,"away":m.away,"league":getattr(m,"league","") or "турнир не определён","minute":int(m.minute or 0),"score":[int(m.home_score or 0),int(m.away_score or 0)],"xg":pair(s,"xg"),"shots":pair(s,"shots"),"shots_on_target":pair(s,"shots_on_target"),"big_chances":pair(s,"big_chances"),"corners":pair(s,"corners"),"shots_inside_box":pair(s,"shots_inside_box"),"touches_box":pair(s,"touches_box"),"goal_times":goals(m)}
def send(m,v,model):
 prob=int(v.get("goal_probability") or 0);h=int(v.get("horizon_minutes") or 0);league=getattr(m,"league","") or "турнир не определён";now_msk=datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M")
 text=f"🤖 <b>GEMINI LIVE SCOUT</b>\n🕒 <b>{now_msk} МСК</b>\n\n🏆 <b>{league}</b>\n⚽ <b>{m.home} — {m.away}</b>\n⏱ {m.minute}' | {m.home_score}:{m.away_score}\n\n🔥 <b>ВИЖУ ЕЩЁ ГОЛ</b>\n📊 Оценка AI: <b>{prob}%</b>\n⏳ Горизонт: ~{h} мин\n🧠 Уверенность: {v.get('confidence','')}\n\n💬 {v.get('reason','')}\n⚠️ Риск: {v.get('risk','')}\n\n<i>Независимый анализ сырых LIVE-данных · {model}</i>"
 return unified_bot.telegram_send(text)
def scan(live):
 now=time.time();c=[]
 for m in live:
  minute=int(getattr(m,"minute",0) or 0)
  if minute<MINUTE_MIN or minute>MINUTE_MAX or getattr(m,"is_halftime",False):continue
  old=_seen.get(str(m.event_id));score=(int(m.home_score or 0),int(m.away_score or 0))
  if old and now-old[0]<RECHECK and old[1]==score:continue
  c.append(m)
 stats={}
 if c:
  with ThreadPoolExecutor(max_workers=min(WORKERS,len(c))) as ex:
   for f in as_completed([ex.submit(fetch_one,m) for m in c]):m,s=f.result();stats[str(m.event_id)]=s
 def activity(m):
  s=stats.get(str(m.event_id),{});return sum(pair(s,"shots_on_target"))*5+sum(pair(s,"big_chances"))*6+sum(pair(s,"xg"))*4+sum(pair(s,"shots"))*.5
 ready=[m for m in c if useful(stats.get(str(m.event_id),{}))];ready.sort(key=activity,reverse=True);sent=0;checked=0
 for m in ready[:MAX_AI_PER_CYCLE]:
  s=stats[str(m.event_id)];v,e,model=ask(payload(m,s));checked+=1;_seen[str(m.event_id)]=(now,(int(m.home_score or 0),int(m.away_score or 0)))
  if not v:logger.warning("GEMINI_SCOUT_FAILED %s %s",m.event_id,e);continue
  d=str(v.get("decision") or "");prob=int(v.get("goal_probability") or 0);logger.warning("GEMINI_SCOUT %d' %s — %s %d:%d | %s %d%% | model=%s",m.minute,m.home,m.away,m.home_score,m.away_score,d,prob,model)
  if d=="ENTER" and prob>=ENTER_PROB and send(m,v,model):sent+=1
 logger.info("GEMINI_SCOUT_CYCLE live=%d data_candidates=%d ai_checked=%d sent=%d",len(live),len(ready),checked,sent);return sent
