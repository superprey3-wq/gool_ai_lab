"""GOOL TENNIS — independent second Telegram bot, Flashscore-only analysis."""
from __future__ import annotations
import asyncio,logging,os,shutil,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent;BASE=ROOT/"_gool_base"
BASE_REPO=os.getenv("GOOL_BASE_REPO","https://github.com/superprey3-wq/gool_bot.git")
BASE_REF=os.getenv("GOOL_BASE_REF","e4a70ae663c24a0162e43982c05570e72174a870")
INTERVAL=max(20,int(os.getenv("TENNIS_SCAN_INTERVAL_SECONDS","35")))
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s");logger=logging.getLogger("gool_tennis")

def prep():
    marker=BASE/".lab_ref"
    try:current=marker.read_text("utf-8").strip()
    except:current=""
    if current==BASE_REF and (BASE/"gool_bot").exists():return
    if BASE.exists():shutil.rmtree(BASE,ignore_errors=True)
    subprocess.run(["git","clone","--depth","1","--quiet",BASE_REPO,str(BASE)],check=True)
    subprocess.run(["git","-C",str(BASE),"fetch","--depth","1","origin",BASE_REF],check=True)
    subprocess.run(["git","-C",str(BASE),"checkout","--quiet",BASE_REF],check=True)
    marker.write_text(BASE_REF,"utf-8")

prep();BOT_DIR=BASE/"gool_bot";sys.path.insert(0,str(BOT_DIR));sys.path.insert(0,str(ROOT))
from telegram_subscribers import polling_loop
import tennis_runtime

async def cycle():
    try:
        started=time.monotonic();sent=await asyncio.to_thread(tennis_runtime.scan_once)
        logger.info("GOOL_TENNIS_CYCLE sent=%d total=%.1fs",sent,time.monotonic()-started)
    except Exception:logger.exception("GOOL TENNIS cycle failed")

async def main():
    logger.warning("GOOL TENNIS START | FLASHSCORE ONLY | SET WINNER CORE + SET TOTAL CORE | early-set gate=%d..%d games | winner>=%d%% total>=%d%%",tennis_runtime.tennis_core.EARLY_MIN_GAMES,tennis_runtime.tennis_core.EARLY_MAX_GAMES,round(tennis_runtime.tennis_core.WINNER_MIN_PROB*100),round(tennis_runtime.tennis_core.TOTAL_MIN_PROB*100))
    poller=asyncio.create_task(polling_loop(),name="tennis-telegram-poller")
    try:
        while True:
            started=time.monotonic();await cycle();await asyncio.sleep(max(3,INTERVAL-(time.monotonic()-started)))
    finally:
        poller.cancel();await asyncio.gather(poller,return_exceptions=True)

if __name__=="__main__":asyncio.run(main())
