"""GOOL TENNIS probability engine: Flashscore-only decisions."""
from __future__ import annotations
from functools import lru_cache
import os

EARLY_MIN_GAMES=int(os.getenv("TENNIS_EARLY_MIN_GAMES","2"))
EARLY_MAX_GAMES=int(os.getenv("TENNIS_EARLY_MAX_GAMES","5"))
WINNER_MIN_PROB=float(os.getenv("TENNIS_WINNER_MIN_PROB","0.72"))
TOTAL_MIN_PROB=float(os.getenv("TENNIS_TOTAL_MIN_PROB","0.70"))
MIN_STATS_KEYS=int(os.getenv("TENNIS_MIN_STATS_KEYS","2"))
TOTAL_LINES=(8.5,9.5,10.5,11.5,12.5)
USEFUL_STATS={"aces","double_faults","first_serve_pct","first_serve_won_pct","second_serve_won_pct","break_points_saved","break_points_won","service_points_won","return_points_won","total_points_won"}

def _pair(stats,key,default):
    v=stats.get(key)
    if not v:return default
    try:return float(v[0]),float(v[1])
    except:return default

def _pct(v,fallback):
    if v<=0:return fallback
    return max(.25,min(.90,v/100 if v>1 else v))

def stats_quality(stats):
    keys=sorted(k for k in stats if k in USEFUL_STATS);return len(keys),keys

def game_hold_probability(point_win):
    p=max(.35,min(.85,point_win));q=1-p
    before=p**4*(1+4*q+10*q*q);deuce=20*p**3*q**3;wd=(p*p)/max(1e-9,1-2*p*q)
    return max(.30,min(.95,before+deuce*wd))

def estimate_holds(stats,is_wta=False):
    base=.60 if is_wta else .62
    fs=_pair(stats,"first_serve_pct",(62,62));fsw=_pair(stats,"first_serve_won_pct",(70,70));ssw=_pair(stats,"second_serve_won_pct",(50,50));dfs=_pair(stats,"double_faults",(0,0));service=_pair(stats,"service_points_won",(0,0));returns=_pair(stats,"return_points_won",(0,0))
    out=[]
    for i in range(2):
        p=_pct(fs[i],.62)*_pct(fsw[i],.70)+(1-_pct(fs[i],.62))*_pct(ssw[i],.50)
        if service[i]>0:p=.60*p+.40*_pct(service[i],p)
        opp=1-i
        if returns[opp]>0:p-=max(-.025,min(.025,(_pct(returns[opp],.36)-.36)*.18))
        p-=min(.025,max(0,dfs[i])*.004);p=.75*p+.25*base;out.append(game_hold_probability(p))
    return out[0],out[1]

def _terminal(a,b):
    if (a>=6 or b>=6) and abs(a-b)>=2:return 1 if a>b else 2
    if a==7 and b==6:return 1
    if b==7 and a==6:return 2
    return 0

def project_set(g1,g2,h1,h2,next_server=0):
    def solve(server0):
        @lru_cache(maxsize=None)
        def rec(a,b,server):
            w=_terminal(a,b)
            if w:return (1.0 if w==1 else 0.0,{a+b:1.0})
            if a==6 and b==6:
                p1=max(.30,min(.70,.5+(h1-h2)*.75));return p1,{13:1.0}
            pg=h1 if server==1 else 1-h2;pg=max(.08,min(.92,pg));ns=2 if server==1 else 1
            pa,da=rec(a+1,b,ns);pb,db=rec(a,b+1,ns);dist={}
            for t,p in da.items():dist[t]=dist.get(t,0)+pg*p
            for t,p in db.items():dist[t]=dist.get(t,0)+(1-pg)*p
            return pg*pa+(1-pg)*pb,dist
        return rec(max(0,g1),max(0,g2),server0)
    if next_server in (1,2):p1,dist=solve(next_server)
    else:
        p1a,da=solve(1);p1b,db=solve(2);p1=(p1a+p1b)/2;dist={k:(da.get(k,0)+db.get(k,0))/2 for k in set(da)|set(db)}
    return {"p1":p1,"p2":1-p1,"totals":dist}

def over_probability(dist,line):return sum(p for games,p in dist.items() if games>line)

def _best_total(dist):
    choices=[]
    for line in TOTAL_LINES:
        over=over_probability(dist,line);under=1-over
        if over>=TOTAL_MIN_PROB:choices.append((over-TOTAL_MIN_PROB,over,"OVER",line))
        if under>=TOTAL_MIN_PROB:choices.append((under-TOTAL_MIN_PROB,under,"UNDER",line))
    if not choices:return None
    # Prefer the most decisive projection; for equal confidence prefer the central line.
    choices.sort(key=lambda x:(x[0],x[1],-abs(x[3]-9.5)),reverse=True)
    _,prob,pick,line=choices[0]
    return pick,line,prob

def analyse(match,stats):
    if not EARLY_MIN_GAMES<=match.games_played<=EARLY_MAX_GAMES:return []
    quality,keys=stats_quality(stats)
    if quality<MIN_STATS_KEYS:return []
    is_wta="wta" in (match.tournament or "").lower() or "women" in (match.tournament or "").lower()
    h1,h2=estimate_holds(stats,is_wta);proj=project_set(match.games1,match.games2,h1,h2,match.server);out=[]

    winner_side=1 if proj["p1"]>=proj["p2"] else 2
    winner_prob=proj[f"p{winner_side}"]
    out.append({"core":"SET_WINNER_CORE","pick":f"P{winner_side}","line":None,"probability":winner_prob,"entry":winner_prob>=WINNER_MIN_PROB,"hold1":h1,"hold2":h2,"stats_quality":quality,"stats_keys":keys})

    total=_best_total(proj["totals"])
    if total:
        pick,line,prob=total
        out.append({"core":"SET_TOTAL_CORE","pick":pick,"line":line,"probability":prob,"entry":prob>=TOTAL_MIN_PROB,"hold1":h1,"hold2":h2,"stats_quality":quality,"stats_keys":keys})

    # Send a card only when at least one market is strong enough to be an entry.
    return out if any(x.get("entry") for x in out) else []
