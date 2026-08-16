"""Lightweight LIVE goal probability engine for GOOL AI SCOUT.

No scipy/pandas/numpy: designed for the 256 MB deployment. This is not a fitted
pre-match Dixon-Coles model; it is a transparent in-play Poisson-style baseline
that estimates P(at least one more goal) from time remaining + live attacking data.
It exists as an independent second opinion for Gemini and for later calibration.
"""
from __future__ import annotations

import math


def _pair(stats,key):
    try:
        a,b=stats.get(key,(0,0));return float(a or 0),float(b or 0)
    except Exception:return 0.0,0.0


def estimate(match,stats,pressure=0.0,momentum=0.0):
    minute=max(1,int(getattr(match,"minute",0) or 0))
    # Include a modest stoppage allowance; cap protects malformed minute values.
    remaining=max(0.0,min(95.0-minute,90.0))
    if remaining<=0:return {"probability":1.0,"lambda_remaining":0.0,"quality":0,"label":"NO_TIME"}

    xgh,xga=_pair(stats,"xg");sh,sa=_pair(stats,"shots");sth,sta=_pair(stats,"shots_on_target")
    bch,bca=_pair(stats,"big_chances");ibh,iba=_pair(stats,"shots_inside_box");tbh,tba=_pair(stats,"touches_box")
    xg=xgh+xga;shots=sh+sa;sot=sth+sta;bc=bch+bca;ibox=ibh+iba;touches=tbh+tba

    # Observed attacking tempo per elapsed minute, converted to a conservative
    # expected-goal rate. xG is strongest when present; other terms provide a
    # fallback when a feed lacks xG.
    elapsed=max(10.0,float(min(minute,90)))
    xg_rate=xg/elapsed if xg>0 else 0.0
    proxy=(0.030*sot+0.018*bc+0.0035*ibox+0.0007*touches+0.0015*shots)
    proxy_rate=proxy/max(1.0,elapsed/45.0)
    live_rate=(0.72*xg_rate+0.28*(proxy_rate/45.0)) if xg>0 else max(0.010,proxy_rate/45.0)

    # League-neutral prior ~2.55 goals/90, blended more strongly when live data is sparse.
    prior_rate=2.55/90.0
    evidence=min(1.0,(shots+2*sot+3*bc)/30.0)
    rate=prior_rate*(1.0-evidence*0.72)+live_rate*(evidence*0.72)

    # Pressure/momentum are bounded modifiers, not dominant inputs.
    pressure_factor=0.82+0.0032*max(0.0,min(float(pressure or 0),100.0))
    momentum_factor=1.0+max(-0.10,min(0.10,float(momentum or 0)/500.0))
    lam=max(0.02,min(3.5,rate*remaining*pressure_factor*momentum_factor))
    prob=(1.0-math.exp(-lam))*100.0

    quality=0
    if xg>0:quality+=35
    if shots>0:quality+=20
    if sot>0:quality+=20
    if bc>0:quality+=10
    if ibox>0 or touches>0:quality+=10
    if pressure:quality+=5
    quality=min(100,quality)
    label="HIGH" if prob>=70 else "MEDIUM" if prob>=52 else "LOW"
    return {"probability":round(prob,1),"lambda_remaining":round(lam,3),"quality":quality,"label":label,"remaining":round(remaining,1)}
