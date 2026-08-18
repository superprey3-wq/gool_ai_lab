"""GOOL TENNIS live scanner and Telegram delivery — Flashscore only."""
from __future__ import annotations
import json,logging,os,time
from pathlib import Path
import requests
from telegram_subscribers import get_subscribers
import tennis_core,tennis_flashscore

logger=logging.getLogger("tennis_runtime")
STORE=Path(os.getenv("TENNIS_SIGNAL_STORE","tennis_signals.json"))
RECHECK=int(os.getenv("TENNIS_RECHECK_SECONDS","45"))
_seen={}

def _load():
    try:
        x=json.loads(STORE.read_text("utf-8"));return x if isinstance(x,list) else []
    except:return []
def _save(rows):STORE.write_text(json.dumps(rows,ensure_ascii=False,indent=2),"utf-8")
def _has_signal(event_id,set_no):return any(str(r.get("event_id"))==str(event_id) and int(r.get("set_no",0))==set_no for r in _load())
def _record(match,signal):
    rows=_load();rows.append({"id":f"{match.event_id}:{match.set_no}:{int(time.time())}","created_ts":int(time.time()),"result":"pending","event_id":match.event_id,"player1":match.player1,"player2":match.player2,"tournament":match.tournament,"surface":match.surface,"set_no":match.set_no,"sets_at_signal":[match.sets1,match.sets2],"games_at_signal":[match.games1,match.games2],**signal});_save(rows)
def _pct(x):return f"{round(float(x)*100)}%"

def _message(match,signal):
    if signal["core"]=="SET_WINNER_CORE":
        side=1 if signal["pick"]=="P1" else 2;player=match.player1 if side==1 else match.player2
        title="🏆 <b>SET WINNER CORE</b>";pick=f"Победа {player} в {match.set_no}-м сете"
    else:
        title="📈 <b>SET TOTAL CORE</b>";pick=f"ТБ {signal['line']:g} в {match.set_no}-м сете"
    return "\n".join(["🎾 <b>GOOL TENNIS · ВХОД</b>",f"{match.player1} — {match.player2}",f"🏟 {match.tournament or 'турнир не определён'}",f"Сет {match.set_no} · геймы <b>{match.games1}:{match.games2}</b>","",title,f"🔥 <b>{pick}</b>",f"📊 Вероятность GOOL: <b>{_pct(signal['probability'])}</b>",f"🎯 Hold-модель: {_pct(signal['hold1'])} / {_pct(signal['hold2'])}",f"📚 LIVE-показателей учтено: <b>{signal.get('stats_quality',0)}</b>","","ℹ️ Решение рассчитано только по LIVE-счёту и статистике Flashscore."])

def _send(text):
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    if not token:logger.warning("TENNIS Telegram disabled: token missing");return False
    recipients=get_subscribers()
    if not recipients:logger.warning("TENNIS Telegram: no subscribers");return False
    ok=0
    for cid in recipients:
        try:
            r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":str(cid),"text":text,"parse_mode":"HTML","disable_web_page_preview":True},timeout=20)
            if r.ok:ok+=1
            else:logger.warning("TENNIS Telegram failed chat=%s http=%s",cid,r.status_code)
        except requests.RequestException as e:logger.warning("TENNIS Telegram failed %s",e)
    return ok>0

def _close_signals(live_by_id):
    rows=_load();changed=False
    for r in rows:
        if r.get("result")!="pending":continue
        m=live_by_id.get(str(r.get("event_id")))
        if m is None:continue
        entry_set=int(r.get("set_no",0))
        if m.set_no<=entry_set:continue
        old_sets=r.get("sets_at_signal") or [0,0];d1=m.sets1-int(old_sets[0]);d2=m.sets2-int(old_sets[1])
        if d1==d2:continue
        actual="P1" if d1>d2 else "P2"
        if r.get("core")=="SET_WINNER_CORE":
            r["result"]="win" if actual==r.get("pick") else "loss"
        else:
            # Total result will be finalised from completed-set score in the next calibration step.
            r["result"]="void"
        r["closed_ts"]=int(time.time());changed=True
        logger.warning("TENNIS RESULT id=%s set=%d core=%s result=%s",r.get("event_id"),entry_set,r.get("core"),r.get("result"))
    if changed:_save(rows)

def scan_once():
    live=tennis_flashscore.discover_live();live_by_id={str(m.event_id):m for m in live};_close_signals(live_by_id)
    logger.info("TENNIS SOURCE Flashscore=%d | bookmaker=OFF",len(live))
    sent=0;candidates=0;with_stats=0;now=time.time()
    for match in live:
        if not tennis_core.EARLY_MIN_GAMES<=match.games_played<=tennis_core.EARLY_MAX_GAMES:continue
        candidates+=1
        if _has_signal(match.event_id,match.set_no):continue
        snap=(match.set_no,match.games1,match.games2);old=_seen.get(match.event_id)
        if old and now-old[0]<RECHECK and old[1:]==snap:continue
        _seen[match.event_id]=(now,*snap)
        stats=tennis_flashscore.fetch_stats(match.event_id)
        quality,keys=tennis_core.stats_quality(stats)
        if stats:with_stats+=1
        logger.info("TENNIS ANALYZE id=%s set=%d games=%d:%d server=%s stats_quality=%d keys=%s | %s — %s",match.event_id,match.set_no,match.games1,match.games2,match.server or "?",quality,keys,match.player1,match.player2)
        signals=tennis_core.analyse(match,stats)
        if not signals:
            logger.info("TENNIS WATCH id=%s set=%d games=%d:%d quality=%d",match.event_id,match.set_no,match.games1,match.games2,quality);continue
        s=signals[0]
        if _send(_message(match,s)):
            _record(match,s);sent+=1
            logger.warning("TENNIS ENTER id=%s set=%d core=%s pick=%s line=%s probability=%.1f%%",match.event_id,match.set_no,s["core"],s.get("pick"),s.get("line"),s["probability"]*100)
    logger.info("TENNIS CYCLE flashscore=%d early_candidates=%d with_stats=%d sent=%d",len(live),candidates,with_stats,sent);return sent
