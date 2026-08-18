"""Flashscore tennis LIVE adapter for GOOL TENNIS."""
from __future__ import annotations
from dataclasses import dataclass, field
import logging, re
from typing import Any
from live_engine import _feed

logger=logging.getLogger("tennis_flashscore")
LIVE_STATUS="2"
TENNNIS_FEEDS=("f_2_0_2_en-gb_1","f_2_0_0_en_1")

def _fields(raw:str)->dict[str,str]:
    out={}
    for token in raw.split("¬"):
        if "÷" in token:
            k,v=token.split("÷",1)
            if k: out[k]=v
    return out

def _as_int(v:Any,default:int=0)->int:
    try:return int(float(str(v)))
    except:return default

def _number(v:Any):
    if v is None:return None
    m=re.search(r"-?\d+(?:[.,]\d+)?",str(v).replace("%",""))
    if not m:return None
    try:return float(m.group(0).replace(",","."))
    except:return None

@dataclass
class TennisMatch:
    event_id:str; player1:str; player2:str; tournament:str; surface:str
    sets1:int; sets2:int; games1:int; games2:int
    point1:str=""; point2:str=""; server:int=0; status:str=""; raw:dict[str,str]=field(default_factory=dict)
    @property
    def set_no(self): return max(1,self.sets1+self.sets2+1)
    @property
    def games_played(self): return self.games1+self.games2

STAT_ALIASES={
 "aces":("aces","ace"),"double_faults":("double faults","double fault"),
 "first_serve_pct":("1st serve %","first serve %","1st serve percentage"),
 "first_serve_won_pct":("1st serve points won","first serve points won"),
 "second_serve_won_pct":("2nd serve points won","second serve points won"),
 "break_points_saved":("break points saved",),"break_points_won":("break points converted","break points won"),
 "service_points_won":("service points won",),"return_points_won":("return points won",),"total_points_won":("total points won",),}

def _stat_name(chunk):
    p=_fields(chunk)
    for k in ("SE","SG","SC","SA","SD"):
        v=str(p.get(k) or "").strip()
        if v and not v.isdigit():return v.lower()
    return chunk.lower()

def parse_stats(body):
    out={}
    for chunk in body.split("~"):
        f=_fields(chunk); l=_number(f.get("SH")); r=_number(f.get("SI"))
        if l is None or r is None:continue
        label=_stat_name(chunk)
        for name,aliases in STAT_ALIASES.items():
            if any(a in label for a in aliases):out[name]=(l,r);break
    return out

def fetch_stats(event_id):
    body=_feed(f"df_st_1_{event_id}")
    return parse_stats(body) if body else {}

def _surface(t):
    low=t.lower()
    for s in ("hard","clay","grass","carpet"):
        if s in low:return s
    return ""

def _score_candidates(f:dict[str,str], sets1:int, sets2:int):
    """Try known Flashscore tennis score field families, but never confuse set score with games."""
    pairs=[("GRA","GRB"),("IGA","IGB"),("JA","JB"),("KA","KB"),("DA","DB"),("EA","EB")]
    found=[]
    for a,b in pairs:
        if a in f and b in f:
            x,y=_as_int(f.get(a),-1),_as_int(f.get(b),-1)
            if 0<=x<=7 and 0<=y<=7 and (x,y)!=(sets1,sets2): found.append((a,b,x,y))
    return found

def parse_master(body:str):
    matches=[]; tournament=""; singles=True
    for chunk in body.split("~"):
        f=_fields(chunk)
        if "ZA" in f:
            tournament=(f.get("ZA") or "").strip(); low=tournament.lower(); singles="doubles" not in low; continue
        eid=(f.get("AA") or "").strip()
        if not eid or f.get("AB")!=LIVE_STATUS or not singles:continue
        p1=(f.get("AE") or "").strip(); p2=(f.get("AF") or "").strip()
        if not p1 or not p2:continue
        sets1=_as_int(f.get("AG")); sets2=_as_int(f.get("AH"))
        candidates=_score_candidates(f,sets1,sets2)
        games1=games2=0
        if candidates:
            _,_,games1,games2=candidates[0]
        point1=str(f.get("ERA") or f.get("OA") or ""); point2=str(f.get("ERB") or f.get("OB") or "")
        server=_as_int(f.get("SERV") or f.get("KJ") or 0)
        matches.append(TennisMatch(eid,p1,p2,tournament,_surface(tournament),sets1,sets2,games1,games2,point1,point2,server,f"AB={f.get('AB')} AC={f.get('AC','')}",f))
    return list({m.event_id:m for m in matches}.values())

def discover_live():
    for feed in TENNNIS_FEEDS:
        body=_feed(feed)
        if not body:continue
        rows=parse_master(body)
        if rows:
            logger.info("FLASHSCORE TENNIS LIVE feed=%s matches=%d",feed,len(rows))
            # During calibration expose compact raw numeric fields for first live rows.
            for m in rows[:8]:
                nums={k:v for k,v in m.raw.items() if re.fullmatch(r"-?\d+(?:\.\d+)?",str(v or "")) and len(k)<=4}
                logger.info("TENNIS FS RAW id=%s %s — %s fields=%s",m.event_id,m.player1,m.player2,nums)
            return rows
    logger.warning("FLASHSCORE TENNIS LIVE: no rows parsed")
    return []
