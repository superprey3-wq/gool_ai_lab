"""1xBet LIVE tennis odds adapter for GOOL TENNIS.

Flashscore remains the source of truth for score and statistics. This module is
used only for live prices. 1xBet moves traffic between regional domains, so the
adapter probes several official mirrors and both VZip/Zip endpoints.
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
ROOTS = [x.strip().rstrip("/") for x in os.getenv(
    "XBET_ROOTS",
    "https://1xbet.cr,https://1xbet.com,https://dz.1xbet.com,https://mda.1xbet.com",
).split(",") if x.strip()]
SPORT_ID = int(os.getenv("XBET_TENNIS_SPORT_ID", "4"))
COUNTRY = int(os.getenv("XBET_COUNTRY", "1"))
PARTNER = int(os.getenv("XBET_PARTNER", "55"))
LANG = os.getenv("XBET_LANG", "en")
TIMEOUT = int(os.getenv("XBET_TIMEOUT", "12"))


@dataclass
class XbetEvent:
    event_id: int
    player1: str
    player2: str
    league: str
    raw: dict[str, Any]
    root: str = ""


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


def _headers(root: str) -> dict[str, str]:
    return {
        "Accept": "*/*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137 Safari/537.36",
        "Referer": root + "/en/live/tennis",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Mode": "cors",
    }


def _request(root: str, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    url = root + "/LiveFeed/" + path
    try:
        r = requests.get(url, params=params, headers=_headers(root), timeout=TIMEOUT, allow_redirects=True)
        ctype = str(r.headers.get("content-type") or "")
        if not r.ok:
            logger.warning("1XBET FAIL root=%s path=%s http=%s", root, path, r.status_code)
            return None
        try:
            data = r.json()
        except ValueError:
            logger.warning("1XBET NONJSON root=%s path=%s http=%s type=%s body=%s", root, path, r.status_code, ctype, r.text[:120].replace("\n", " "))
            return None
        if isinstance(data, dict):
            rows = data.get("Value")
            n = len(rows) if isinstance(rows, list) else (1 if isinstance(rows, dict) else 0)
            logger.info("1XBET OK root=%s path=%s value=%d", root, path, n)
            return data
    except requests.RequestException as exc:
        logger.warning("1XBET ERROR root=%s path=%s %s", root, path, exc)
    return None


def _sports_probe(root: str) -> None:
    data = _request(root, "GetSportsShortZip", {
        "sports": 0, "lng": LANG, "tf": 1000000, "country": COUNTRY,
        "partner": PARTNER, "virtualSports": "true", "groupChamps": "true",
    })
    rows = (data or {}).get("Value") or []
    tennis = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("N") or row.get("E") or row.get("SN") or "")
        if "tennis" in name.lower():
            tennis.append((row.get("I"), name, row.get("C")))
    if tennis:
        logger.info("1XBET SPORTS tennis=%s", tennis[:5])


def live_events() -> list[XbetEvent]:
    common = {
        "sports": SPORT_ID,
        "count": 1000,
        "lng": LANG,
        "mode": 4,
        "country": COUNTRY,
        "partner": PARTNER,
        "getEmpty": "true",
    }
    for root in ROOTS:
        for path in ("Get1x2_VZip", "Get1x2_Zip"):
            data = _request(root, path, common)
            rows = (data or {}).get("Value") or []
            if not isinstance(rows, list) or not rows:
                continue
            out: list[XbetEvent] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    eid = int(row.get("I"))
                except (TypeError, ValueError):
                    continue
                p1 = str(row.get("O1") or "").strip()
                p2 = str(row.get("O2") or "").strip()
                if not p1 or not p2:
                    continue
                out.append(XbetEvent(eid, p1, p2, str(row.get("L") or row.get("LE") or ""), row, root))
            if out:
                logger.info("1XBET TENNIS LIVE parsed=%d root=%s path=%s sample=%s — %s", len(out), root, path, out[0].player1, out[0].player2)
                return out
        _sports_probe(root)
    logger.warning("1XBET TENNIS LIVE parsed=0 across roots=%s sport=%s partner=%s country=%s", ROOTS, SPORT_ID, PARTNER, COUNTRY)
    return []


def match_event(player1: str, player2: str, events: list[XbetEvent] | None = None, threshold: float = 0.68) -> XbetEvent | None:
    events = events if events is not None else live_events()
    best: tuple[float, XbetEvent] | None = None
    for event in events:
        direct = (_similar(player1, event.player1) + _similar(player2, event.player2)) / 2
        swapped = (_similar(player1, event.player2) + _similar(player2, event.player1)) / 2
        score = max(direct, swapped)
        if best is None or score > best[0]:
            best = (score, event)
    if best:
        logger.info("1XBET MATCH %s — %s => %.3f %s — %s", player1, player2, best[0], best[1].player1, best[1].player2)
    if best and best[0] >= threshold:
        return best[1]
    return None


def game(event: XbetEvent | int) -> dict[str, Any] | None:
    eid = event.event_id if isinstance(event, XbetEvent) else int(event)
    roots = [event.root] + [x for x in ROOTS if x != event.root] if isinstance(event, XbetEvent) and event.root else ROOTS
    params = {
        "id": eid, "lng": LANG, "cfview": 0, "isSubGames": "true",
        "GroupEvents": "true", "allEventsGroupSubGames": "true",
        "countevents": 250, "partner": PARTNER, "grMode": 2, "country": COUNTRY,
    }
    for root in roots:
        data = _request(root, "GetGameZip", params)
        value = (data or {}).get("Value")
        if isinstance(value, dict):
            return value
    return None


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
    return " ".join(str(node.get(k) or "") for k in ("N", "GN", "G", "T", "P", "PL", "O", "CN", "PN")).lower()


def extract_set_markets(payload: dict[str, Any] | None, set_no: int) -> dict[str, Any]:
    result: dict[str, Any] = {"p1": None, "p2": None, "totals": {}}
    if not payload:
        return result
    set_tokens = (f"set {set_no}", f"{set_no} set", f"set{set_no}", f"сет {set_no}", f"{set_no}-й сет")
    interesting = []
    for node in _walk(payload):
        odd = _odd(node)
        if odd is None:
            continue
        label = _label(node)
        if label:
            interesting.append((label[:120], odd, node.get("P"), node.get("T")))
        if label and ("set" in label or "сет" in label) and not any(tok in label for tok in set_tokens):
            continue
        in_set = any(tok in label for tok in set_tokens)
        if in_set and any(x in label for x in ("player 1", "p1", "1 wins", "home", "first player", "winner 1")):
            result["p1"] = odd
        elif in_set and any(x in label for x in ("player 2", "p2", "2 wins", "away", "second player", "winner 2")):
            result["p2"] = odd
        if in_set and ("total" in label or "over" in label or "больше" in label):
            param = node.get("P") or node.get("PL") or node.get("H")
            try:
                line = float(param)
            except (TypeError, ValueError):
                m = re.search(r"(8\.5|9\.5|10\.5|11\.5|12\.5)", label)
                line = float(m.group(1)) if m else None
            if line is not None and ("over" in label or "больше" in label):
                result["totals"][line] = odd
    if result["p1"] is None and result["p2"] is None and not result["totals"]:
        logger.info("1XBET MARKETS set=%d unresolved sample=%s", set_no, interesting[:12])
    else:
        logger.info("1XBET MARKETS set=%d p1=%s p2=%s totals=%s", set_no, result["p1"], result["p2"], result["totals"])
    return result


def odds_for_match(player1: str, player2: str, set_no: int, cache: list[XbetEvent] | None = None) -> dict[str, Any]:
    event = match_event(player1, player2, cache)
    if not event:
        return {"event_id": None, "p1": None, "p2": None, "totals": {}}
    markets = extract_set_markets(game(event), set_no)
    markets["event_id"] = event.event_id
    return markets
