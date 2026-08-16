from __future__ import annotations
import asyncio,logging,os
from live_engine import fetch_summary
import score_sync_patch
import unified_bot
import ai_signal_journal as journal
logger=logging.getLogger('ai_goal_watch')
INTERVAL=max(15,int(os.getenv('AI_GOAL_WATCH_SECONDS','20')))
def _score(s):
    try:a,b=str(s).split(':',1);return int(a),int(b)
    except:return 0,0
def scan_once():
    found=0
    for r in journal.pending():
        try:
            body=fetch_summary(r.get('event_id'))
            if not body:continue
            current,goal_minute=score_sync_patch._summary_state(body)
            if current is None:continue
            before=_score(r.get('score_at_signal'))
            if sum(current)>sum(before):
                if journal.close(r.get('id'),'win',f'{current[0]}:{current[1]}',goal_minute):
                    text=(f"✅ <b>ГОЛ! GEMINI SCOUT ЗАШЁЛ</b>\n\n⚽ <b>{r.get('home')} — {r.get('away')}</b>\n🏆 {r.get('league') or 'турнир не указан'}\n⏱ Вход: {r.get('minute')}' | {r.get('score_at_signal')}\n⚽ Новый счёт: <b>{current[0]}:{current[1]}</b>" + (f"\n🥅 Гол: ~{goal_minute}'" if goal_minute else '') + f"\n🤖 Оценка Gemini была: <b>{r.get('probability')}%</b>")
                    unified_bot.telegram_send(text);logger.warning('AI_GOAL_CONFIRMED %s %s -> %s',r.get('event_id'),before,current);found+=1
        except Exception as exc:logger.info('AI_GOAL_WATCH_FAILED %s: %s',r.get('event_id'),exc)
    return found
async def loop():
    logger.info('AI GOAL WATCH started every %ss',INTERVAL)
    while True:
        await asyncio.to_thread(scan_once);await asyncio.sleep(INTERVAL)
