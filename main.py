"""Low-memory independent Gemini LIVE scout.
Flashscore collection stays technical; Gemini alone makes the football decision.
Production GOOL is untouched.
"""
from __future__ import annotations
import asyncio,logging,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT/"_gool_base"
BASE_REPO=os.getenv("GOOL_BASE_REPO","https://github.com/superprey3-wq/gool_bot.git");BASE_REF=os.getenv("GOOL_BASE_REF","e4a70ae663c24a0162e43982c05570e72174a870")
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s");logger=logging.getLogger("gool_ai_lab")
def prep():
 marker=BASE/".lab_ref"
 try:current=marker.read_text("utf-8").strip()
 except:current=""
 if current==BASE_REF and (BASE/"gool_bot").exists():return
 if BASE.exists():shutil.rmtree(BASE,ignore_errors=True)
 subprocess.run(["git","clone","--depth","1","--quiet",BASE_REPO,str(BASE)],check=True);subprocess.run(["git","-C",str(BASE),"fetch","--depth","1","origin",BASE_REF],check=True);subprocess.run(["git","-C",str(BASE),"checkout","--quiet",BASE_REF],check=True);marker.write_text(BASE_REF,"utf-8")
prep();BOT_DIR=BASE/"gool_bot";sys.path.insert(0,str(BOT_DIR));sys.path.insert(0,str(ROOT))
os.environ.setdefault("GEMINI_SHADOW_ENABLED","0");os.environ.setdefault("GEMINI_TELEGRAM_VISIBLE","0");os.environ.setdefault("AI_SCOUT_TEXT_ONLY","1")
INTERVAL=max(60,int(os.getenv("GEMINI_SCOUT_INTERVAL_SECONDS","90")))
import visual_feed_unified_bot
import score_sync_patch
from telegram_subscribers import polling_loop
import gemini_live_scout
import ai_goal_watch

async def cycle():
 try:
  t=time.monotonic();live=await visual_feed_unified_bot.unified_bot.discover_live_matches();sent=await asyncio.to_thread(gemini_live_scout.scan,live);logger.info("PURE_GEMINI_CYCLE live=%d sent=%d total=%.1fs",len(live),sent,time.monotonic()-t)
 except Exception:logger.exception("PURE GEMINI cycle failed")
async def main():
 ok,reason=visual_feed_unified_bot.telegram_config_status();logger.warning("GEMINI LIVE SCOUT START | independent Flashscore analyst | fresh-live recheck ON | goal watch ON | report ON | Telegram=%s","OK" if ok else reason)
 poller=asyncio.create_task(polling_loop(),name='ai-telegram-poller');goal_watch=asyncio.create_task(ai_goal_watch.loop(),name='ai-goal-watch')
 try:
  while True:
   t=time.monotonic();await cycle();await asyncio.sleep(max(3,INTERVAL-(time.monotonic()-t)))
 finally:
  poller.cancel();goal_watch.cancel();await asyncio.gather(poller,goal_watch,return_exceptions=True)
if __name__=="__main__":asyncio.run(main())
