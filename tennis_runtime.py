"""GOOL TENNIS live scanner and Telegram delivery."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time
from datetime import datetime, timezone, timedelta

import requests

from telegram_subscribers import get_subscribers
import tennis_core
import tennis_flashscore
import tennis_xbet

logger = logging.getLogger("tennis_runtime")
MSK = timezone(timedelta(hours=3))
STORE = Path(os.getenv("TENNIS_SIGNAL_STORE", "tennis_signals.json"))
RECHECK = int(os.getenv("TENNIS_RECHECK_SECONDS", "45"))
_seen: dict[str, tuple[float, int, int, int]] = {}


def _load() -> list[dict]:
    try:
        rows = json.loads(STORE.read_text("utf-8"))
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _save(rows: list[dict]) -> None:
    STORE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")


def _has_signal(event_id: str, set_no: int) -> bool:
    return any(str(r.get("event_id")) == str(event_id) and int(r.get("set_no", 0)) == set_no for r in _load())


def _record(match, signal: dict, odds_event_id) -> None:
    rows = _load()
    rows.append({
        "id": f"{match.event_id}:{match.set_no}:{int(time.time())}",
        "created_ts": int(time.time()),
        "result": "pending",
        "event_id": match.event_id,
        "xbet_event_id": odds_event_id,
        "player1": match.player1,
        "player2": match.player2,
        "tournament": match.tournament,
        "surface": match.surface,
        "set_no": match.set_no,
        "sets_at_signal": [match.sets1, match.sets2],
        "games_at_signal": [match.games1, match.games2],
        **signal,
    })
    _save(rows)


def _fmt_pct(x: float) -> str:
    return f"{round(float(x) * 100)}%"


def _message(match, signal: dict) -> str:
    if signal["core"] == "SET_WINNER_CORE":
        side = 1 if signal["pick"] == "P1" else 2
        player = match.player1 if side == 1 else match.player2
        bet = f"Победа {player} в {match.set_no}-м сете"
        title = "🏆 <b>SET WINNER CORE</b>"
    else:
        bet = f"ТБ {signal['line']:g} в {match.set_no}-м сете"
        title = "📈 <b>SET TOTAL CORE</b>"
    edge = signal.get("edge", 0.0)
    return "\n".join([
        "🎾 <b>GOOL TENNIS · ВХОД</b>",
        f"{match.player1} — {match.player2}",
        f"🏟 {match.tournament or 'турнир не определён'}",
        f"Сет {match.set_no} · геймы <b>{match.games1}:{match.games2}</b>",
        "",
        title,
        f"🔥 <b>{bet}</b>",
        f"📊 GOOL: <b>{_fmt_pct(signal['probability'])}</b>",
        f"💰 1xBet: <b>{signal['odd']:.2f}</b>",
        f"⚡ Value: <b>+{edge*100:.1f} п.п.</b>",
        f"🎯 Hold-модель: {_fmt_pct(signal['hold1'])} / {_fmt_pct(signal['hold2'])}",
        "",
        "ℹ️ Сигнал рассчитан в ранней фазе сета по LIVE-статистике Flashscore и линии 1xBet.",
    ])


def _send(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return False
    delivered = 0
    for cid in get_subscribers():
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": str(cid), "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
            if r.ok:
                delivered += 1
            else:
                logger.warning("TENNIS Telegram failed chat=%s http=%s", cid, r.status_code)
        except requests.RequestException as exc:
            logger.warning("TENNIS Telegram failed chat=%s %s", cid, exc)
    return delivered > 0


def _close_winner_signals(live_by_id: dict[str, object]) -> None:
    rows = _load()
    changed = False
    for r in rows:
        if r.get("result") != "pending" or r.get("core") != "SET_WINNER_CORE":
            continue
        match = live_by_id.get(str(r.get("event_id")))
        if match is None:
            continue
        entry_set = int(r.get("set_no", 0))
        if match.set_no <= entry_set:
            continue
        old_sets = r.get("sets_at_signal") or [0, 0]
        d1 = match.sets1 - int(old_sets[0])
        d2 = match.sets2 - int(old_sets[1])
        if d1 == d2:
            continue
        actual = "P1" if d1 > d2 else "P2"
        r["result"] = "win" if actual == r.get("pick") else "loss"
        r["closed_ts"] = int(time.time())
        changed = True
    if changed:
        _save(rows)


def scan_once() -> int:
    live = tennis_flashscore.discover_live()
    live_by_id = {str(m.event_id): m for m in live}
    _close_winner_signals(live_by_id)
    xbet_events = tennis_xbet.live_events()
    sent = 0
    now = time.time()
    for match in live:
        if match.games_played < tennis_core.EARLY_MIN_GAMES or match.games_played > tennis_core.EARLY_MAX_GAMES:
            continue
        if _has_signal(match.event_id, match.set_no):
            continue
        snapshot = (match.set_no, match.games1, match.games2)
        old = _seen.get(match.event_id)
        if old and now - old[0] < RECHECK and old[1:] == snapshot:
            continue
        _seen[match.event_id] = (now, *snapshot)
        stats = tennis_flashscore.fetch_stats(match.event_id)
        odds = tennis_xbet.odds_for_match(match.player1, match.player2, match.set_no, xbet_events)
        signals = tennis_core.analyse(match, stats, odds)
        if not signals:
            logger.info("TENNIS WATCH set=%d %s — %s games=%d:%d odds=%s", match.set_no, match.player1, match.player2, match.games1, match.games2, bool(odds.get("event_id")))
            continue
        signal = signals[0]
        if _send(_message(match, signal)):
            _record(match, signal, odds.get("event_id"))
            sent += 1
            logger.warning("TENNIS ENTER %s set=%d %s %.1f%% @ %.2f", match.event_id, match.set_no, signal["core"], signal["probability"]*100, signal["odd"])
    logger.info("TENNIS CYCLE flashscore=%d xbet=%d sent=%d", len(live), len(xbet_events), sent)
    return sent
