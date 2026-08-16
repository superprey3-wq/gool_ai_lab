"""AI-first controller for GOOL AI SCOUT.

GOOL computes football features; Gemini makes the final ENTER/WATCH/REJECT choice.
Hard safety gates remain non-overridable. Successful AI ENTER decisions are promoted
so the experimental bot can select matches that production GOOL itself would skip.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

import live_candidate_patch as lc

logger=logging.getLogger("gool_ai_first")
MODEL=os.getenv("GEMINI_MODEL","gemini-2.5-flash").strip() or "gemini-2.5-flash"
API_KEY=os.getenv("GEMINI_API_KEY","").strip()
TIMEOUT=max(5,int(os.getenv("AI_FIRST_TIMEOUT_SECONDS","18")))
MIN_PROB=max(1,min(99,int(os.getenv("AI_FIRST_MIN_PROB","67"))))
CACHE_SECONDS=max(30,int(os.getenv("AI_FIRST_CACHE_SECONDS","150")))
FAIL_OPEN=os.getenv("AI_FIRST_FAIL_OPEN","0").strip().lower() in {"1","true","yes","on"}
OUT=Path(os.getenv("AI_FIRST_JOURNAL","ai_first_decisions.jsonl"))

_SCHEMA={"type":"OBJECT","properties":{"decision":{"type":"STRING","enum":["ENTER","WATCH","REJECT"]},"goal_probability":{"type":"INTEGER","minimum":1,"maximum":99},"confidence":{"type":"STRING","enum":["LOW","MEDIUM","HIGH"]},"reason":{"type":"STRING"},"risk":{"type":"STRING"}},"required":["decision","goal_probability","confidence","reason","risk"]}
_orig_evaluate=lc._evaluate
_HARD_BLOCK_ROUTES={"WARMUP_OR_POST_GOAL","ROBUST_POST_GOAL_5M"}
_CACHE={}


def _pair(stats,key):
    try:a,b=stats.get(key,(0,0));return [float(a or 0),float(b or 0)]
    except Exception:return [0.0,0.0]


def _prompt(payload):
    return (
        "Ты главный LIVE-исследователь GOOL AI SCOUT. Ты НЕ подтверждаешь решение старого алгоритма, а самостоятельно выбираешь, есть ли ценность во входе на ЕЩЁ ОДИН гол. "
        "GOOL MASTER и стратегии — лишь дополнительные признаки. Особенно оцени оставшееся время, текущий счёт, силу давления, xG, удары, удары в створ, big chances, штрафную, угловые и momentum. "
        "ENTER — сейчас есть самостоятельное основание ждать ещё гол; WATCH — матч интересный, но вход преждевременный; REJECT — пропустить. "
        "Будь строже при крупном счёте, слабых ударах в створ и затухающем давлении. Не придумывай отсутствующие данные. Верни только JSON.\n\nDATA:\n"+
        json.dumps(payload,ensure_ascii=False)
    )


def _extract(data):
    try:return json.loads("".join(str(p.get("text") or "") for p in data["candidates"][0]["content"]["parts"] if isinstance(p,dict)).strip())
    except Exception:return None


def _ask(payload):
    if not API_KEY:return None,"missing_api_key"
    eid=payload["event_id"];now=time.time();cached=_CACHE.get(eid)
    if cached and now-cached[0]<CACHE_SECONDS and cached[1].get("score")==payload.get("score"):
        return dict(cached[2]),None
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body={"contents":[{"role":"user","parts":[{"text":_prompt(payload)}]}],"generationConfig":{"temperature":0.1,"maxOutputTokens":260,"response_mime_type":"application/json","response_schema":_SCHEMA}}
    started=time.monotonic()
    try:r=requests.post(url,headers={"x-goog-api-key":API_KEY,"Content-Type":"application/json"},json=body,timeout=TIMEOUT)
    except requests.RequestException as exc:return None,f"request:{exc}"
    if not r.ok:return None,f"http:{r.status_code}:{r.text[:160]}"
    verdict=_extract(r.json())
    if not verdict:return None,"bad_json"
    verdict["latency_s"]=round(time.monotonic()-started,2)
    _CACHE[eid]=(now,{"score":payload.get("score")},dict(verdict))
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
    base=_orig_evaluate(m,s,p,goals,market)
    gool_qualifies,route,master,sc,hz,mkt=base
    if str(route or "") in _HARD_BLOCK_ROUTES:
        logger.info("AI_FIRST_HARD_BLOCK %s %s' route=%s",getattr(m,"event_id",""),getattr(m,"minute",0),route)
        return False,route,master,sc,hz,mkt
    payload={"event_id":str(getattr(m,"event_id","") or ""),"home":str(getattr(m,"home","") or ""),"away":str(getattr(m,"away","") or ""),"league":str(getattr(m,"league","") or ""),"minute":int(getattr(m,"minute",0) or 0),"score":[int(getattr(m,"home_score",0) or 0),int(getattr(m,"away_score",0) or 0)],"gool_master":round(float(master or 0),1),"gool_route":route,"gool_qualifies":bool(gool_qualifies),"pressure":round(float(getattr(p,"score",0) or 0),1),"momentum":round(float(getattr(p,"momentum",0) or 0),1),"strategies":{k:round(float(v or 0),1) for k,v in dict(sc or {}).items()},"xg":_pair(s,"xg"),"shots":_pair(s,"shots"),"shots_on_target":_pair(s,"shots_on_target"),"big_chances":_pair(s,"big_chances"),"corners":_pair(s,"corners"),"shots_inside_box":_pair(s,"shots_inside_box"),"touches_box":_pair(s,"touches_box"),"hazards":list(hz or []),"market":mkt or {},"goal_times":list(goals or [])}
    verdict,error=_ask(payload)
    if verdict:
        decision=str(verdict.get("decision") or "REJECT").upper();prob=int(verdict.get("goal_probability") or 0)
        ai_enter=decision=="ENTER" and prob>=MIN_PROB
        ai_route=f"AI_{decision}_{prob}"
        # fast_core_runtime normally requires ENTRY/STRONG grade. Promote a genuine AI ENTER
        # to that transport threshold without altering the logged original GOOL master.
        transport_master=max(float(master or 0),75.0) if ai_enter else float(master or 0)
        logger.warning("AI_FIRST %s' %s — %s %s:%s | GOOL=%.0f | %s %d%% %s | enter=%s",payload["minute"],payload["home"],payload["away"],payload["score"][0],payload["score"][1],master,decision,prob,verdict.get("confidence"),ai_enter)
        _append({"ts":int(time.time()),"payload":payload,"verdict":verdict,"final_enter":ai_enter})
        return ai_enter,ai_route,transport_master,sc,hz,mkt
    logger.warning("AI_FIRST_FAILED %s %s | fail_open=%s",payload["event_id"],error,FAIL_OPEN)
    _append({"ts":int(time.time()),"payload":payload,"error":error,"fallback":FAIL_OPEN})
    if FAIL_OPEN:return base
    return False,"AI_UNAVAILABLE",master,sc,hz,mkt


lc._evaluate=_evaluate
logger.warning("GOOL AI SCOUT: Gemini final selector enabled | min_prob=%d | cache=%ss | fail_open=%s",MIN_PROB,CACHE_SECONDS,FAIL_OPEN)
