"""Give the experimental bot a distinct AI Scout identity.

The production formatter still provides all factual match/stat details. This wrapper
adds an explicit AI-research header and exposes Gemini's probability encoded in the
AI route, so the second Telegram bot is visibly not a clone of production GOOL.
"""
from __future__ import annotations

import re
import live_candidate_patch as lc

_orig_format = lc._format_strategy_signal
_AI_ROUTE = re.compile(r"^AI_(ENTER|WATCH|REJECT)_(\d{1,2})$")


def _format(m,p,s,recs,goals,reason,route,master,hz,market):
    body = _orig_format(m,p,s,recs,goals,reason,route,master,hz,market)
    match = _AI_ROUTE.match(str(route or ""))
    if not match:
        return body
    decision, probability = match.groups()
    title = {
        "ENTER": "🧠 <b>GOOL AI SCOUT · AI-ВХОД</b>",
        "WATCH": "👁 <b>GOOL AI SCOUT · НАБЛЮДАЮ</b>",
        "REJECT": "⛔ <b>GOOL AI SCOUT · ПРОПУСК</b>",
    }.get(decision, "🧠 <b>GOOL AI SCOUT</b>")
    return (
        f"{title}\n"
        f"🤖 Финальное решение: <b>Gemini</b>\n"
        f"🎯 Оценка ещё одного гола: <b>{probability}%</b>\n"
        f"<i>GOOL здесь собирает признаки; выбор матча делает AI.</i>\n\n"
        + body
    )


lc._format_strategy_signal = _format
