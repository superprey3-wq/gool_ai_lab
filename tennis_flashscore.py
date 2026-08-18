"""Flashscore tennis LIVE adapter for GOOL TENNIS."""
from __future__ import annotations
from dataclasses import dataclass, field
import logging,re
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
            if k:out[k]=v
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
    def set_no(self):return max(1,self.sets1+self.sets2+1)
    @property
    def games_played(self):return self.games1+self.games2

STAT_ALIASES={"aces":("aces","ace"),"double_faults":("double faults","double fault"),"first_serve_pct":("1st serve %","first serve %","1st serve percentage"),"first_serve_won_pct":("1st serve points won","first serve points won"),"second_serve_won_pct":("2nd serve points won","second serve points won"),"break_points_saved":("break points saved",),"break_points_won":("break points converted","break points won"),"service_points_won":("service points won",),"return_points_won":("return points won",),"total_points_won":("total points won",)}

def _stat_name(chunk):
    p=_fields(chunk)
    for k in ("SE","SG","SC","SA","SD"):
        v=str(p.get(k) or "").strip()
        if v and not v.isdigit():return v.lower()
    return chunk.lower()
def parse_stats(body):
    out={}
    for chunk in body.split("~"):
        f=_fields(chunk);l=_number(f.get("SH"));r=_number(f.get("SI"))
        if l is None or r is None:continue
        label=_stat_name(chunk)
        for name,aliases in STAT_ALIASES.items():
            if any(a in label for a in aliases):out[name]=(l,r);break
    return out
def fetch_stats(event_id):
    body=_feed(f"df_st_1_{event_id}");return parse_stats(body) if body else {}
def _surface(t):
    low=t.lower()
    for s in ("hard","clay","grass","carpet"):
        if s in low:return s
    return ""

# Flashscore uses period-pair fields for partial tennis scores. The exact family
# can differ between feed variants, so keep an ordered set of known families.
PERIOD_PAIRS=[("BA","BB"),("BC","BD"),("BE","BF"),("BG","BH"),("BI","BJ"),("BK","BL"),("CA","CB"),("CC","CD"),("CE","CF"),("CG","CH"),("DA","DB"),("DC","DD"),("EA","EB"),("EC","ED"),("GRA","GRB"),("IGA","IGB")]

def _valid_games(x,y):return 0<=x<=7 and 0<=y<=7 and x+y<=13

def _period_scores(f):
    out=[]
    for a,b in PERIOD_PAIRS:
        if a in f and b in f:
            x,y=_as_int(f.get(a),-1),_as_int(f.get(b),-1)
            if _valid_games(x,y):out.append((a,b,x,y))
    return out

def _pick_current_games(f,sets1,sets2):
    pairs=_period_scores(f)
    if not pairs:return 0,0,"none"
    set_no=max(1,sets1+sets2+1)
    # Prefer a period pair by current set index among score-like pairs. A zero pair
    # is allowed only if every candidate is zero; otherwise choose the latest
    # plausible non-zero pair, which matches Flashscore's live list semantics.
    nonzero=[p for p in pairs if p[2] or p[3]]
    pool=nonzero or pairs
    idx=min(set_no-1,len(pool)-1)
    chosen=pool[idx] if len(pool)>=set_no else pool[-1]
    return chosen[2],chosen[3],f"{chosen[0]}/{chosen[1]}"

def _point(v):
    s=str(v or "").strip()
    return s if s in {"0","15","30","40","A","AD"} else ""

def parse_master(body:str):
    matches=[];tournament="";singles=True
    for chunk in body.split("~"):
        f=_fields(chunk)
        if "ZA" in f:
            tournament=(f.get("ZA") or "").strip();low=tournament.lower();singles="doubles" not in low;continue
        eid=(f.get("AA") or "").strip()
        if not eid or f.get("AB")!=LIVE_STATUS or not singles:continue
        p1=(f.get("AE") or "").strip();p2=(f.get("AF") or "").strip()
        if not p1 or not p2:continue
        sets1=_as_int(f.get("AG"));sets2=_as_int(f.get("AH"))
        games1,games2,source=_pick_current_games(f,sets1,sets2)
        point1=_point(f.get("ERA") or f.get("OA") or f.get("PA"));point2=_point(f.get("ERB") or f.get("OB") or f.get("PB"))
        server=_as_int(f.get("SERV") or f.get("KJ") or f.get("AS") or 0)
        f=dict(f);f["__games_source"]=source
        matches.append(TennisMatch(eid,p1,p2,tournament,_surface(tournament),sets1,sets2,games1,games2,point1,point2,server,f"AB={f.get('AB')} AC={f.get('AC','')}",f))
    return list({m.event_id:m for m in matches}.values())

def discover_live():
    for feed in TENNNIS_FEEDS:
        body=_feed(feed)
        if not body:continue
        rows=parse_master(body)
        if rows:
            logger.info("FLASHSCORE TENNIS LIVE feed=%s matches=%d",feed,len(rows))
            for m in rows[:12]:
                pairs=_period_scores(m.raw)
                logger.info("TENNIS FS RAW id=%s set=%d sets=%d:%d games=%d:%d src=%s pairs=%s | %s — %s",m.event_id,m.set_no,m.sets1,m.sets2,m.games1,m.games2,m.raw.get("__games_source"),pairs,m.player1,m.player2)
            return rows
    logger.warning("FLASHSCORE TENNIS LIVE: no rows parsed");return []
