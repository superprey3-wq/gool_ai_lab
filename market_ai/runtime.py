import logging,time
from .config import CONFIG
from .storage import Store
from .scoring import score_flow
from .telegram import send
from .resource_guard import rss_mb
from .collectors import BrowserCollector
from .collectors import oddsportal,flashscore

logging.basicConfig(level=logging.INFO,format='%(asctime)s | %(levelname)s | %(message)s')
log=logging.getLogger('GOOL_MARKET_AI')

def _alert_text(q,s):
    return (f'🔥 <b>GOOL MARKET AI</b>\n\n⚽ <b>{q.home} — {q.away}</b>\n'
            f'📈 {q.market} · <b>{q.selection}</b>{" "+str(q.line) if q.line is not None else ""}\n'
            f'💹 движение: <b>{s["move_pct"]:+.2f}%</b> · подтверждают {s["breadth"]}/{s["books"]}\n'
            f'⚡ velocity {s["velocity"]} · persistence {s["persistent"]} · reversal {s["reversals"]}\n'
            f'🧠 Market Score: <b>{s["score"]}/100</b>')

def run():
    store=Store(CONFIG.db_path); browser=BrowserCollector(); started=time.time()
    log.info('GOOL MARKET AI | browser+flow+fairvalue foundation | poll=%ss threshold=%.1f',CONFIG.poll_seconds,CONFIG.alert_score)
    while True:
        cycle=time.time(); quotes=[]
        try:
            if rss_mb() > CONFIG.browser_max_rss_mb:
                log.warning('RESOURCE browser recycle rss=%.1fMB',rss_mb()); browser.close(); started=time.time()
            if time.time()-started > CONFIG.browser_restart_minutes*60:
                log.info('BROWSER periodic recycle'); browser.close(); started=time.time()
            for collector in (oddsportal.collect,flashscore.collect):
                try: quotes.extend(collector(browser) or [])
                except Exception as e: log.warning('COLLECTOR_FAILED %s: %s',collector.__module__,e)
            if quotes:
                store.add(quotes); now=time.time()
                seen=set()
                for q in quotes:
                    k=(q.event_id,q.market,q.selection,q.line)
                    if k in seen: continue
                    seen.add(k); s=score_flow(store.history(q,now-600),now)
                    if not s or s['score'] < CONFIG.alert_score: continue
                    alert_key='|'.join(map(str,k))
                    if store.can_alert(alert_key,now,CONFIG.cooldown_seconds):
                        ok=send(CONFIG.telegram_token,CONFIG.telegram_chat_id,_alert_text(q,s))
                        if ok: store.mark_alert(alert_key,now,s['score']); log.info('MARKET_ALERT_SENT %s score=%.1f',alert_key,s['score'])
            log.info('CYCLE quotes=%d rss=%.1fMB elapsed=%.1fs',len(quotes),rss_mb(),time.time()-cycle)
        except KeyboardInterrupt: break
        except Exception: log.exception('CYCLE_FAILED')
        time.sleep(max(5,CONFIG.poll_seconds-(time.time()-cycle)))
    browser.close()
