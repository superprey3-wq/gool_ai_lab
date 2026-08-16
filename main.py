"""Low-memory standalone GOOL AI SCOUT runner.

This lab is intentionally different from production GOOL: it runs CORE-only, lets
Gemini make the final football selection, disables the duplicate Gemini shadow pass,
and avoids HT/LATE scans so it can fit a small hosting plan.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT/"_gool_base"
BASE_REPO=os.getenv("GOOL_BASE_REPO","https://github.com/superprey3-wq/gool_bot.git")
BASE_REF=os.getenv("GOOL_BASE_REF","e4a70ae663c24a0162e43982c05570e72174a870")

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
logger=logging.getLogger("gool_ai_lab")


def _prepare_base():
    marker=BASE/".lab_ref"
    current=""
    try:current=marker.read_text("utf-8").strip()
    except Exception:pass
    if current==BASE_REF and (BASE/"gool_bot").exists():return
    if BASE.exists():shutil.rmtree(BASE,ignore_errors=True)
    logger.warning("AI SCOUT cloning GOOL baseline %s @ %s",BASE_REPO,BASE_REF)
    subprocess.run(["git","clone","--depth","1","--quiet",BASE_REPO,str(BASE)],check=True)
    subprocess.run(["git","-C",str(BASE),"fetch","--depth","1","origin",BASE_REF],check=True)
    subprocess.run(["git","-C",str(BASE),"checkout","--quiet",BASE_REF],check=True)
    marker.write_text(BASE_REF,"utf-8")


_prepare_base()
BOT_DIR=BASE/"gool_bot"
if str(BOT_DIR) not in sys.path:sys.path.insert(0,str(BOT_DIR))
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

# Small-host defaults. Can be overridden from Env without code changes.
os.environ.setdefault("GEMINI_SHADOW_ENABLED","0")
os.environ.setdefault("GEMINI_TELEGRAM_VISIBLE","0")
os.environ.setdefault("LIVE_SIGNAL_THRESHOLD","45")
os.environ.setdefault("LIVE_COOLDOWN_MINUTES","10")
os.environ.setdefault("AI_FIRST_MIN_PROB","67")
os.environ.setdefault("AI_FIRST_CACHE_SECONDS","150")
os.environ.setdefault("AI_SCOUT_TEXT_ONLY","1")
LIVE_INTERVAL_SECONDS=max(45,int(os.getenv("LIVE_INTERVAL_SECONDS","75")))

# Base football/data stack.
import visual_feed_unified_bot
import live_candidate_patch
import core_warmup_patch
import halftime_hazard_patch
import period_market_patch
import phase_market_patch
import score_sync_patch
import market_math_patch
import gool_xg_consensus
import telegram_signal_filter_patch
import telegram_image_signal_patch
import entry_sync_failopen_patch
import core_result_card_patch
import robust_goal_cooldown_patch

# Gemini owns selection in this lab.
import ai_first_patch
import ai_scout_identity_patch
import fast_core_runtime
fast_core_runtime.MAX_STATS_WORKERS=max(2,int(os.getenv("AI_SCOUT_STATS_WORKERS","4")))
fast_core_runtime.CHEAP_PREFILTER=float(os.getenv("AI_SCOUT_CHEAP_PREFILTER","45"))

# Keep journal/outcome tracking, but deliberately do not start HT HUNTER or LATE RISK.
import signal_journal_runtime_patch
import goal_reset_patch
import live_status_heartbeat
import fast_goal_watch
import engine_result_reconcile_patch
from telegram_subscribers import polling_loop
import production_logging


async def run_live():
    try:
        started=time.monotonic()
        # fast_core_runtime performs discovery exactly once. Do not pre-discover here.
        sent=await visual_feed_unified_bot.unified_bot.scan_live_once()
        logger.info("AI_SCOUT_CYCLE_DONE sent=%s total=%.1fs",sent,time.monotonic()-started)
    except Exception:
        logger.exception("AI SCOUT cycle failed; runner will continue")


async def status_loop():
    while True:
        await asyncio.sleep(live_status_heartbeat.STATUS_INTERVAL_SECONDS)
        try:await asyncio.to_thread(live_status_heartbeat.send_heartbeat)
        except Exception:logger.exception("AI SCOUT heartbeat failed")


async def main():
    tg_ok,tg_reason=visual_feed_unified_bot.telegram_config_status()
    logger.warning("GOOL AI SCOUT START | Gemini final selector | CORE-only | workers=%d | Telegram=%s",fast_core_runtime.MAX_STATS_WORKERS,"OK" if tg_ok else tg_reason)
    poller=asyncio.create_task(polling_loop(),name="ai-scout-telegram-poller")
    heartbeat=asyncio.create_task(status_loop(),name="ai-scout-heartbeat")
    goal_watch=asyncio.create_task(fast_goal_watch.loop(),name="ai-scout-goal-watch")
    try:
        while True:
            started=time.monotonic();await run_live()
            await asyncio.sleep(max(3.0,LIVE_INTERVAL_SECONDS-(time.monotonic()-started)))
    finally:
        poller.cancel();heartbeat.cancel();goal_watch.cancel()
        await asyncio.gather(poller,heartbeat,goal_watch,return_exceptions=True)


if __name__=="__main__":asyncio.run(main())
