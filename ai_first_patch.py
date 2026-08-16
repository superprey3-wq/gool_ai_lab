"""AI-first controller for GOOL AI LAB.

GOOL still computes all football features, MASTER, pressure and hazards. Gemini gets
those features plus the raw live stats and makes the final ENTER/WATCH/REJECT choice.
This module is experimental and is intentionally isolated from production GOOL.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

import live_candidate_patch as lc

logger = logging.getLogger("gool_ai_first")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TIMEOUT = max(5, int(os.getenv("AI_FIRST_TIMEOUT_SECONDS", "20")))
MIN_PROB = max(1, min(99, int(os.getenv("AI_FIRST_MIN_PROB", "65"))))
FAIL_OPEN = os.getenv("AI_FIRST_FAIL_OPEN", "0").strip().lower() in {"1", "true", "yes", "on"}
OUT = Path(os.getenv("AI_FIRST_JOURNAL", "ai_first_decisions.jsonl"))

_SCHEMA = {
    "type":"OBJECT",
    "properties":{
        "decision":{"type":"STRING","enum":["ENTER","WATCH","REJECT"]},
        "goal_probability":{"type":"INTEGER","minimum":1,"maximum":99},
        "confidence":{"type":"STRING","enum":["LOW","MEDIUM","HIGH"]},
        "reason":{"type":"STRING"},
        "risk":{"type":"STRING"}
    },
    "required":["decision","goal_probability","confidence","reason","risk"]
}

_orig_evaluate = lc._evaluate


def _pair(stats, key):
    try:
        a,b = stats.get(key,(0,0)); return [float(a or 0), float(b or 0)]
    except Exception:
        return [0.0,0.0]


def _prompt(payload):
    return (
        "Ты главный LIVE-исследователь экспериментальной системы GOOL AI LAB. "
        "Твоя задача — решить, оправдан ли вход на ЕЩЁ ОДИН гол после текущей точки. "
        "GOOL MASTER и внутренние стратегии — только признаки, а не приказ. "
        "Учитывай минуту, счёт, xG, удары, удары в створ, big chances, штрафную, угловые, "
        "давление, momentum, историю стратегий и оставшееся время. После недавнего гола будь строже. "
        "ENTER — вход оправдан сейчас; WATCH — интересно, но пока рано; REJECT — слабый вход. "
        "Не придумывай отсутствующие данные. Верни только JSON по схеме.\n\nDATA:\n"+
        json.dumps(payload,ensure_ascii=False)
    )


def _extract(data):
    try:
        text="".join(str(p.get("text") or "") for p in data["candidates"][0]["content"]["parts"] if isinstance(p,dict)).strip()
        return json.loads(text)
    except Exception:
        return None


def _ask(payload):
    if not API_KEY:
        return None, "missing_api_key"
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body={
        "contents":[{"role":"user","parts":[{"text":_prompt(payload)}]}],
        "generationConfig":{
            "temperature":0.1,
            "maxOutputTokens":320,
            "response_mime_type":"application/json",
            "response_schema":_SCHEMA,
        },
    }
    started=time.monotonic()
    try:
        r=requests.post(url,headers={"x-goog-api-key":API_KEY,"Content-Type":"application/json"},json=body,timeout=TIMEOUT)
    except requests.RequestException as exc:
        return None, f"request:{exc}"
    if not r.ok:
        return None, f"http:{r.status_code}:{r.text[:160]}"
    verdict=_extract(r.json())
    if not verdict:
        return None, "bad_json"
    verdict["latency_s"]=round(time.monotonic()-started,2)
    return verdict, None


def _append(row):
    try:
        with OUT.open("a",encoding="utf-8") as f:
            f.write(json.dumps(row,ensure_ascii=False)+"\n")
    except Exception as exc:
        logger.warning("AI_FIRST_SAVE_FAILED %s",exc)


def _evaluate(m,s,p,goals,market):
    base=_orig_evaluate(m,s,p,goals,market)
    gool_qualifies,route,master,sc,hz,mkt=base
    payload={
        "event_id":str(getattr(m,"event_id","") or ""),
        "home":str(getattr(m,"home","") or ""),
        "away":str(getattr(m,"away","") or ""),
        "league":str(getattr(m,"league","") or ""),
        "minute":int(getattr(m,"minute",0) or 0),
        "score":[int(getattr(m,"home_score",0) or 0),int(getattr(m,"away_score",0) or 0)],
        "gool_master":round(float(master or 0),1),
        "gool_route":route,
        "gool_qualifies":bool(gool_qualifies),
        "pressure":round(float(getattr(p,"score",0) or 0),1),
        "momentum":round(float(getattr(p,"momentum",0) or 0),1),
        "strategies":{k:round(float(v or 0),1) for k,v in dict(sc or {}).items()},
        "xg":_pair(s,"xg"),
        "shots":_pair(s,"shots"),
        "shots_on_target":_pair(s,"shots_on_target"),
        "big_chances":_pair(s,"big_chances"),
        "corners":_pair(s,"corners"),
        "shots_inside_box":_pair(s,"shots_inside_box"),
        "touches_box":_pair(s,"touches_box"),
        "hazards":list(hz or []),
        "market":mkt or {},
        "goal_times":list(goals or []),
    }
    verdict,error=_ask(payload)
    if verdict:
        decision=str(verdict.get("decision") or "REJECT").upper()
        prob=int(verdict.get("goal_probability") or 0)
        ai_enter=decision=="ENTER" and prob>=MIN_PROB
        route=f"AI_{decision}_{prob}"
        logger.warning("AI_FIRST %s' %s — %s %s:%s | GOOL=%.0f | %s %d%% %s | enter=%s",payload["minute"],payload["home"],payload["away"],payload["score"][0],payload["score"][1],master,decision,prob,verdict.get("confidence"),ai_enter)
        _append({"ts":int(time.time()),"payload":payload,"verdict":verdict,"final_enter":ai_enter})
        return ai_enter,route,master,sc,hz,mkt

    logger.warning("AI_FIRST_FAILED %s %s | fail_open=%s",payload["event_id"],error,FAIL_OPEN)
    _append({"ts":int(time.time()),"payload":payload,"error":error,"fallback":FAIL_OPEN})
    if FAIL_OPEN:
        return base
    return False,"AI_UNAVAILABLE",master,sc,hz,mkt


lc._evaluate=_evaluate
logger.warning("GOOL AI LAB: AI-FIRST controller enabled | Gemini final decision | min_prob=%d | fail_open=%s",MIN_PROB,FAIL_OPEN)
