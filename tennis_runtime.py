"""GOOL TENNIS live scanner and Telegram delivery."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time
from datetime import timezone, timedelta

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
        "ℹ️ Ранний LIVE-сигнал: Flashscore статистика + линия 1xBet.",
    ])


def _send(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.warning("TENNIS Telegram disabled: TELEGRAM_BOT_TOKEN missing")
        return False
    recipients = get_subscribers()
    if not recipients:
        logger.warning("TENNIS Telegram: no subscribers; send /start to the second bot")
        return False
    delivered = 0
    for cid in recipients:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": str(cid), "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=20,
            )
            if r.ok:
                delivered += 1
            else:
                logger.warning("TENNIS Telegram failed chat=%s http=%s body=%s", cid, r.status_code, r.text[:120])
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
        logger.warning("TENNIS RESULT %s set=%d pick=%s actual=%s result=%s", r.get("event_id"), entry_set, r.get("pick"), actual, r["result"])
    if changed:
        _save(rows)


def scan_once() -> int:
    live = tennis_flashscore.discover_live()
    live_by_id = {str(m.event_id): m for m in live}
    _close_winner_signals(live_by_id)

    xbet_events = tennis_xbet.live_events()
    logger.info("TENNIS SOURCES Flashscore=%d 1xBet=%d", len(live), len(xbet_events))
    for m in live[:8]:
        logger.info(
            "TENNIS FS LIVE id=%s set=%d sets=%d:%d games=%d:%d server=%s | %s — %s",
            m.event_id, m.set_no, m.sets1, m.sets2, m.games1, m.games2, m.server or "?", m.player1, m.player2,
        )

    sent = 0
    now = time.time()
    candidates = 0
    matched_xbet = 0
    with_stats = 0

    for match in live:
        if match.games_played < tennis_core.EARLY_MIN_GAMES or match.games_played > tennis_core.EARLY_MAX_GAMES:
            continue
        candidates += 1
        if _has_signal(match.event_id, match.set_no):
            logger.info("TENNIS SKIP already_signalled id=%s set=%d", match.event_id, match.set_no)
            continue
        snapshot = (match.set_no, match.games1, match.games2)
        old = _seen.get(match.event_id)
        if old and now - old[0] < RECHECK and old[1:] == snapshot:
            continue
        _seen[match.event_id] = (now, *snapshot)

        stats = tennis_flashscore.fetch_stats(match.event_id)
        if stats:
            with_stats += 1
        logger.info("TENNIS STATS id=%s keys=%s", match.event_id, sorted(stats.keys()) if stats else [])

        odds = tennis_xbet.odds_for_match(match.player1, match.player2, match.set_no, xbet_events)
        if odds.get("event_id"):
            matched_xbet += 1
        logger.info(
            "TENNIS XBET id=%s xbet_id=%s p1=%s p2=%s totals=%s",
            match.event_id, odds.get("event_id"), odds.get("p1"), odds.get("p2"), odds.get("totals"),
        )

        signals = tennis_core.analyse(match, stats, odds)
        if not signals:
            logger.info(
                "TENNIS WATCH set=%d %s — %s games=%d:%d stats=%s xbet=%s",
                match.set_no, match.player1, match.player2, match.games1, match.games2, bool(stats), bool(odds.get("event_id")),
            )
            continue

        signal = signals[0]
        if _send(_message(match, signal)):
            _record(match, signal, odds.get("event_id"))
            sent += 1
            logger.warning(
                "TENNIS ENTER %s set=%d %s %.1f%% @ %.2f edge=%.1fpp",
                match.event_id, match.set_no, signal["core"], signal["probability"] * 100, signal["odd"], signal.get("edge", 0) * 100,
            )

    logger.info(
        "TENNIS CYCLE flashscore=%d xbet=%d early_candidates=%d with_stats=%d matched_xbet=%d sent=%d",
        len(live), len(xbet_events), candidates, with_stats, matched_xbet, sent,
    )
    return sent
