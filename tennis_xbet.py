"""1xBet LIVE tennis odds adapter for GOOL TENNIS."""
from __future__ import annotations
from dataclasses import dataclass
import logging, os, re, unicodedata
from difflib import SequenceMatcher
from typing import Any
import requests

logger=logging.getLogger("tennis_xbet")
BASES=[x.strip().rstrip("/")+"/" for x in os.getenv("XBET_LIVE_BASES","https://1xbet.com/LiveFeed/,https://1xbet.cr/LiveFeed/").split(",") if x.strip()]
SPORT_ID=int(os.getenv("XBET_TENNIS_SPORT_ID","4")); COUNTRY=int(os.getenv("XBET_COUNTRY","1")); LANG=os.getenv("XBET_LANG","en"); TIMEOUT=int(os.getenv("XBET_TIMEOUT","12"))
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137 Safari/537.36","Accept":"*/*","X-Requested-With":"XMLHttpRequest"}

@dataclass
class XbetEvent:
    event_id:int; player1:str; player2:str; league:str; raw:dict[str,Any]

def _norm(v:str)->str:
    v=unicodedata.normalize("NFKD",str(v or "")); v="".join(ch for ch in v if not unicodedata.combining(ch)).lower(); v=re.sub(r"[^a-z0-9]+"," ",v).strip(); return " ".join(v.split())
def _similar(a,b):
    a,b=_norm(a),_norm(b)
    if not a or not b:return 0.0
    if a==b:return 1.0
    return SequenceMatcher(None,a,b).ratio()

def _get(path:str,params:dict[str,Any]):
    for base in BASES:
        try:
            r=requests.get(base+path,params=params,headers=HEADERS,timeout=TIMEOUT)
            if not r.ok:
                logger.info("1XBET %s%s http=%s",base,path,r.status_code); continue
            data=r.json()
            if isinstance(data,dict):
                logger.info("1XBET OK %s%s value=%s",base,path,len(data.get("Value") or []) if isinstance(data.get("Value"),list) else bool(data.get("Value")))
                return data
        except (requests.RequestException,ValueError) as exc:
            logger.info("1XBET %s%s failed: %s",base,path,exc)
    return None

def live_events()->list[XbetEvent]:
    params={"getEmpty":"true","count":1000,"lng":LANG,"sports":SPORT_ID,"country":COUNTRY,"mode":4,"antisports":188}
    data=None
    for method in ("Get1x2_VZip","Get1x2_Zip"):
        data=_get(method,params)
        if isinstance((data or {}).get("Value"),list) and (data or {}).get("Value"):break
    rows=(data or {}).get("Value") or []; out=[]
    for row in rows:
        if not isinstance(row,dict):continue
        try:eid=int(row.get("I"))
        except:continue
        p1=str(row.get("O1") or "").strip(); p2=str(row.get("O2") or "").strip()
        if p1 and p2:out.append(XbetEvent(eid,p1,p2,str(row.get("L") or ""),row))
    logger.info("1XBET TENNIS LIVE parsed=%d raw=%d",len(out),len(rows)); return out

def match_event(player1,player2,events=None,threshold=.68):
    events=events if events is not None else live_events(); best=None
    for e in events:
        direct=(_similar(player1,e.player1)+_similar(player2,e.player2))/2; swapped=(_similar(player1,e.player2)+_similar(player2,e.player1))/2; score=max(direct,swapped)
        if best is None or score>best[0]:best=(score,e)
    if best and best[0]>=threshold:
        logger.info("1XBET MATCH %.2f %s/%s -> %s/%s",best[0],player1,player2,best[1].player1,best[1].player2); return best[1]
    return None

def game(event_id:int):
    data=_get("GetGameZip",{"id":event_id,"lng":LANG,"cfview":0,"isSubGames":"true","GroupEvents":"true","countevents":250,"country":COUNTRY})
    v=(data or {}).get("Value"); return v if isinstance(v,dict) else None

def _walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values():yield from _walk(v)
    elif isinstance(obj,list):
        for v in obj:yield from _walk(v)
def _odd(node):
    for k in ("C","K","V","CF"):
        try:
            x=float(node.get(k))
            if x>1:return x
        except:pass
    return None
def _label(node):return " ".join(str(node.get(k) or "") for k in ("N","GN","G","T","P","PL","O","CN")).lower()
def extract_set_markets(payload,set_no):
    result={"p1":None,"p2":None,"totals":{}}
    if not payload:return result
    tokens=(f"set {set_no}",f"{set_no} set",f"set{set_no}",f"сет {set_no}")
    for node in _walk(payload):
        odd=_odd(node)
        if odd is None:continue
        label=_label(node)
        if label and ("set" in label or "сет" in label) and not any(t in label for t in tokens):continue
        if any(t in label for t in tokens):
            if any(x in label for x in ("player 1","p1","1 wins","home")):result["p1"]=odd
            elif any(x in label for x in ("player 2","p2","2 wins","away")):result["p2"]=odd
        if any(t in label for t in tokens) and ("total" in label or "over" in label or "больше" in label):
            param=node.get("P") or node.get("PL") or node.get("H")
            try:line=float(param)
            except:
                m=re.search(r"(8\.5|9\.5|10\.5|11\.5|12\.5)",label); line=float(m.group(1)) if m else None
            if line is not None and ("over" in label or "больше" in label):result["totals"][line]=odd
    return result

def odds_for_match(player1,player2,set_no,cache=None):
    event=match_event(player1,player2,cache)
    if not event:return {"event_id":None,"p1":None,"p2":None,"totals":{}}
    markets=extract_set_markets(game(event.event_id),set_no); markets["event_id"]=event.event_id; return markets
