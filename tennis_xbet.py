"""1xBet LIVE tennis odds adapter.

The public website exposes LiveFeed endpoints used by its own frontend. This
module keeps the transport and parsing isolated from the model so endpoint or
market-code changes do not affect GOOL TENNIS logic.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import requests

logger = logging.getLogger("tennis_xbet")
BASE = os.getenv("XBET_LIVE_BASE", "https://1xbet.com/LiveFeed/").rstrip("/") + "/"
SPORT_ID = int(os.getenv("XBET_TENNIS_SPORT_ID", "4"))
COUNTRY = int(os.getenv("XBET_COUNTRY", "1"))
LANG = os.getenv("XBET_LANG", "en")
TIMEOUT = int(os.getenv("XBET_TIMEOUT", "12"))


@dataclass
class XbetEvent:
    event_id: int
    player1: str
    player2: str
    league: str
    raw: dict[str, Any]


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    return " ".join(value.split())


def _similar(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _get(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    try:
        r = requests.get(BASE + path, params=params, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=TIMEOUT)
        if not r.ok:
            logger.warning("1XBET %s http=%s", path, r.status_code)
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except (requests.RequestException, ValueError) as exc:
        logger.warning("1XBET %s failed: %s", path, exc)
        return None


def live_events() -> list[XbetEvent]:
    data = _get("Get1x2_Zip", {"getEmpty": "true", "count": 1000, "lng": LANG, "sports": SPORT_ID, "country": COUNTRY})
    rows = (data or {}).get("Value") or []
    out: list[XbetEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            eid = int(row.get("I"))
        except (TypeError, ValueError):
            continue
        p1, p2 = str(row.get("O1") or "").strip(), str(row.get("O2") or "").strip()
        if not p1 or not p2:
            continue
        out.append(XbetEvent(eid, p1, p2, str(row.get("L") or ""), row))
    return out


def match_event(player1: str, player2: str, events: list[XbetEvent] | None = None, threshold: float = 0.72) -> XbetEvent | None:
    events = events if events is not None else live_events()
    best: tuple[float, XbetEvent] | None = None
    for event in events:
        direct = (_similar(player1, event.player1) + _similar(player2, event.player2)) / 2
        swapped = (_similar(player1, event.player2) + _similar(player2, event.player1)) / 2
        score = max(direct, swapped)
        if best is None or score > best[0]:
            best = (score, event)
    if best and best[0] >= threshold:
        return best[1]
    return None


def game(event_id: int) -> dict[str, Any] | None:
    data = _get("GetGameZip", {"id": event_id, "lng": LANG, "cfview": 0, "isSubGames": "true", "GroupEvents": "true", "countevents": 250, "country": COUNTRY})
    value = (data or {}).get("Value")
    return value if isinstance(value, dict) else None


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk(value)


def _odd(node: dict[str, Any]) -> float | None:
    for key in ("C", "K", "V", "CF"):
        try:
            value = float(node.get(key))
            if value > 1.0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def _label(node: dict[str, Any]) -> str:
    return " ".join(str(node.get(k) or "") for k in ("N", "GN", "G", "T", "P", "PL", "O", "CN")).lower()


def extract_set_markets(payload: dict[str, Any] | None, set_no: int) -> dict[str, Any]:
    """Best-effort semantic parser for set winner and set totals.

    1xBet market codes vary across frontend versions. We therefore search both
    descriptive labels and numeric parameter/price nodes. Unknown nodes are
    ignored rather than guessed into a signal.
    """
    result: dict[str, Any] = {"p1": None, "p2": None, "totals": {}}
    if not payload:
        return result
    set_tokens = (f"set {set_no}", f"{set_no} set", f"set{set_no}", f"сет {set_no}")
    for node in _walk(payload):
        odd = _odd(node)
        if odd is None:
            continue
        label = _label(node)
        if label and not any(tok in label for tok in set_tokens):
            # Nodes without a text label are allowed below; labelled nodes for
            # other sets are skipped to prevent cross-set contamination.
            if "set" in label or "сет" in label:
                continue
        if any(x in label for x in ("player 1", "p1", "1 wins", "home")) and any(tok in label for tok in set_tokens):
            result["p1"] = odd
        elif any(x in label for x in ("player 2", "p2", "2 wins", "away")) and any(tok in label for tok in set_tokens):
            result["p2"] = odd
        if "total" in label or "over" in label:
            param = node.get("P") or node.get("PL") or node.get("H")
            try:
                line = float(param)
            except (TypeError, ValueError):
                m = re.search(r"(8\.5|9\.5|10\.5|11\.5|12\.5)", label)
                line = float(m.group(1)) if m else None
            if line is not None and ("over" in label or "больше" in label):
                result["totals"][line] = odd
    return result


def odds_for_match(player1: str, player2: str, set_no: int, cache: list[XbetEvent] | None = None) -> dict[str, Any]:
    event = match_event(player1, player2, cache)
    if not event:
        return {"event_id": None, "p1": None, "p2": None, "totals": {}}
    markets = extract_set_markets(game(event.event_id), set_no)
    markets["event_id"] = event.event_id
    return markets
