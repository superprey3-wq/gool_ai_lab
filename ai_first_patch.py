"""AI-first controller for GOOL AI SCOUT.

GOOL computes football features; lightweight MATH independently estimates the chance
of another goal; Gemini makes the final ENTER/WATCH/REJECT choice. Hard safety gates
remain non-overridable.
"""
from __future__ import annotations
import json,logging,os,time
from pathlib import Path
import requests
import live_candidate_patch as lc
import math_engine
logger=logging.getLogger("gool_ai_first")
MODEL=os.getenv("GEMINI_MODEL","gemini-2.5-flash").strip() or "gemini-2.5-flash"
API_KEY=os.getenv("GEMINI_API_KEY","").strip();TIMEOUT=max(5,int(os.getenv("AI_FIRST_TIMEOUT_SECONDS","18")))
MIN_PROB=max(1,min(99,int(os.getenv("AI_FIRST_MIN_PROB","67"))));CACHE_SECONDS=max(30,int(os.getenv("AI_FIRST_CACHE_SECONDS","150")))
FAIL_OPEN=os.getenv("AI_FIRST_FAIL_OPEN","0").strip().lower() in {"1","true","yes","on"};OUT=Path(os.getenv("AI_FIRST_JOURNAL","ai_first_decisions.jsonl"))
_SCHEMA={"type":"OBJECT","properties":{"decision":{"type":"STRING","enum":["ENTER","WATCH","REJECT"]},"goal_probability":{"type":"INTEGER","minimum":1,"maximum":99},"confidence":{"type":"STRING","enum":["LOW","MEDIUM","HIGH"]},"reason":{"type":"STRING"},"risk":{"type":"STRING"}},"required":["decision","goal_probability","confidence","reason","risk"]}
_orig_evaluate=lc._evaluate;_HARD_BLOCK_ROUTES={"WARMUP_OR_POST_GOAL","ROBUST_POST_GOAL_5M"};_CACHE={}
def _pair(stats,key):
    try:a,b=stats.get(key,(0,0));return [float(a or 0),float(b or 0)]
    except Exception:return [0.0,0.0]
def _prompt(payload):
    return ("Ты главный LIVE-исследователь GOOL AI SCOUT. Решай самостоятельно, ждать ли ЕЩЁ ОДИН гол. У тебя три слоя: сырая LIVE-статистика, GOOL и независимый MATH baseline. MATH — не истина и не приказ: учитывай его вероятность и quality, а при расхождении с GOOL объясни, какой сигнал убедительнее. ENTER=вход сейчас, WATCH=интересно но рано, REJECT=пропустить. Будь строже при крупном счёте, слабых ударах в створ и малом оставшемся времени. Не придумывай данные. Верни только JSON.\n\nDATA:\n"+json.dumps(payload,ensure_ascii=False))
def _extract(data):
    try:return json.loads("".join(str(p.get("text") or "") for p in data["candidates"][0]["content"]["parts"] if isinstance(p,dict)).strip())
    except Exception:return None
def _ask(payload):
    if not API_KEY:return None,"missing_api_key"
    eid=payload["event_id"];now=time.time();cached=_CACHE.get(eid)
    if cached and now-cached[0]<CACHE_SECONDS and cached[1].get("score")==payload.get("score"):return dict(cached[2]),None
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent";body={"contents":[{"role":"user","parts":[{"text":_prompt(payload)}]}],"generationConfig":{"temperature":0.1,"maxOutputTokens":260,"response_mime_type":"application/json","response_schema":_SCHEMA}}
    started=time.monotonic()
    try:r=requests.post(url,headers={"x-goog-api-key":API_KEY,"Content-Type":"application/json"},json=body,timeout=TIMEOUT)
    except requests.RequestException as exc:return None,f"request:{exc}"
    if not r.ok:return None,f"http:{r.status_code}:{r.text[:160]}"
    verdict=_extract(r.json())
    if not verdict:return None,"bad_json"
    verdict["latency_s"]=round(time.monotonic()-started,2);_CACHE[eid]=(now,{"score":payload.get("score")},dict(verdict))
    if len(_CACHE)>1000:
        cutoff=now-CACHE_SECONDS*2
        for key,val in list(_CACHE.items()):
            if val[0]<cutoff:_CACHE.pop(key,None)
    return verdict,None
def _append(row):
    try:
        with OUT.open("a",encoding="utf-8") as f:f.write(json.dumps(row,ensure_ascii=False)+"\n")
    except Exception as exc:logger.warning("AI_FIRST_SAVE_FAILED %s",exc)
def _evaluate(m,s,p,goals,market):
    base=_orig_evaluate(m,s,p,goals,market);gool_qualifies,route,master,sc,hz,mkt=base
    if str(route or "") in _HARD_BLOCK_ROUTES:return False,route,master,sc,hz,mkt
    math=math_engine.estimate(m,s,getattr(p,"score",0),getattr(p,"momentum",0))
    payload={"event_id":str(getattr(m,"event_id","") or ""),"home":str(getattr(m,"home","") or ""),"away":str(getattr(m,"away","") or ""),"league":str(getattr(m,"league","") or ""),"minute":int(getattr(m,"minute",0) or 0),"score":[int(getattr(m,"home_score",0) or 0),int(getattr(m,"away_score",0) or 0)],"gool_master":round(float(master or 0),1),"gool_route":route,"gool_qualifies":bool(gool_qualifies),"math":math,"pressure":round(float(getattr(p,"score",0) or 0),1),"momentum":round(float(getattr(p,"momentum",0) or 0),1),"strategies":{k:round(float(v or 0),1) for k,v in dict(sc or {}).items()},"xg":_pair(s,"xg"),"shots":_pair(s,"shots"),"shots_on_target":_pair(s,"shots_on_target"),"big_chances":_pair(s,"big_chances"),"corners":_pair(s,"corners"),"shots_inside_box":_pair(s,"shots_inside_box"),"touches_box":_pair(s,"touches_box"),"hazards":list(hz or []),"market":mkt or {},"goal_times":list(goals or [])}
    verdict,error=_ask(payload)
    if verdict:
        decision=str(verdict.get("decision") or "REJECT").upper();prob=int(verdict.get("goal_probability") or 0);ai_enter=decision=="ENTER" and prob>=MIN_PROB;ai_route=f"AI_{decision}_{prob}";transport_master=max(float(master or 0),75.0) if ai_enter else float(master or 0)
        logger.warning("AI_CONSENSUS %s' %s — %s | GOOL=%.0f MATH=%.1f(q%d) GEMINI=%s %d%% | enter=%s",payload["minute"],payload["home"],payload["away"],master,math["probability"],math["quality"],decision,prob,ai_enter)
        _append({"ts":int(time.time()),"payload":payload,"verdict":verdict,"final_enter":ai_enter});return ai_enter,ai_route,transport_master,sc,hz,mkt
    logger.warning("AI_FIRST_FAILED %s %s | fail_open=%s",payload["event_id"],error,FAIL_OPEN);_append({"ts":int(time.time()),"payload":payload,"error":error,"fallback":FAIL_OPEN})
    if FAIL_OPEN:return base
    return False,"AI_UNAVAILABLE",master,sc,hz,mkt
lc._evaluate=_evaluate
logger.warning("GOOL AI SCOUT: GOOL + MATH + Gemini consensus enabled | min_prob=%d | cache=%ss",MIN_PROB,CACHE_SECONDS)
