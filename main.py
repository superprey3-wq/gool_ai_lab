"""Standalone GOOL AI LAB runner.

At startup this lab clones a pinned production GOOL baseline into a private local
folder, then enables the AI-first controller. Production `gool_bot` is never modified.
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
    logger.warning("AI LAB cloning GOOL baseline %s @ %s",BASE_REPO,BASE_REF)
    subprocess.run(["git","clone","--quiet",BASE_REPO,str(BASE)],check=True)
    subprocess.run(["git","-C",str(BASE),"checkout","--quiet",BASE_REF],check=True)
    marker.write_text(BASE_REF,"utf-8")


_prepare_base()
BOT_DIR=BASE/"gool_bot"
if str(BOT_DIR) not in sys.path:sys.path.insert(0,str(BOT_DIR))
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

os.environ.setdefault("LIVE_SIGNAL_THRESHOLD","75")
os.environ.setdefault("LIVE_COOLDOWN_MINUTES","12")
LIVE_INTERVAL_SECONDS=max(30,int(os.getenv("LIVE_INTERVAL_SECONDS","60")))

# Base data/Telegram pipeline.
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

# AI FIRST must be loaded before fast_core_runtime captures lc._evaluate.
import ai_first_patch
import fast_core_runtime
import signal_journal_runtime_patch
import goal_reset_patch
import live_status_heartbeat
import fast_goal_watch
import multi_engine_runtime
import engine_result_reconcile_patch
from telegram_subscribers import polling_loop
import production_logging


async def run_live():
    try:
        started=time.monotonic()
        live=await visual_feed_unified_bot.unified_bot.discover_live_matches()
        discovery=time.monotonic()-started
        score_sync_patch.reuse_once(live)
        await visual_feed_unified_bot.unified_bot.scan_live_once()
        # HT/LATE remain available for comparison, but CORE final entry is AI-controlled.
        await asyncio.to_thread(multi_engine_runtime.scan_engines,live)
        logger.info("AI_LAB_CYCLE_DONE live=%d discovery=%.1fs total=%.1fs",len(live),discovery,time.monotonic()-started)
    except Exception:
        logger.exception("AI LAB cycle failed; runner will continue")


async def status_loop():
    while True:
        await asyncio.sleep(live_status_heartbeat.STATUS_INTERVAL_SECONDS)
        try:await asyncio.to_thread(live_status_heartbeat.send_heartbeat)
        except Exception:logger.exception("AI LAB heartbeat failed")


async def main():
    tg_ok,tg_reason=visual_feed_unified_bot.telegram_config_status()
    logger.warning("GOOL AI LAB START | Gemini controls CORE final decision | Telegram=%s", "OK" if tg_ok else tg_reason)
    poller=asyncio.create_task(polling_loop(),name="ai-lab-telegram-poller")
    heartbeat=asyncio.create_task(status_loop(),name="ai-lab-heartbeat")
    goal_watch=asyncio.create_task(fast_goal_watch.loop(),name="ai-lab-goal-watch")
    try:
        while True:
            started=time.monotonic()
            await run_live()
            await asyncio.sleep(max(2.0,LIVE_INTERVAL_SECONDS-(time.monotonic()-started)))
    finally:
        poller.cancel();heartbeat.cancel();goal_watch.cancel()
        await asyncio.gather(poller,heartbeat,goal_watch,return_exceptions=True)


if __name__=="__main__":asyncio.run(main())
