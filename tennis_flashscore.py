"""Flashscore tennis LIVE adapter for GOOL TENNIS.

Uses the same Flashscore feed transport as production GOOL, but switches to
sport project 2 (tennis). The adapter intentionally keeps the raw fields so we
can tune mappings against real live matches without losing information.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Any

from live_engine import _feed

logger = logging.getLogger("tennis_flashscore")

LIVE_STATUS = "2"
TENNNIS_FEEDS = ("f_2_0_2_en-gb_1", "f_2_0_0_en_1")


def _fields(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in raw.split("¬"):
        if "÷" not in token:
            continue
        key, value = token.split("÷", 1)
        if key:
            out[key] = value
    return out


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _number(value: Any) -> float | None:
    if value is None:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value).replace("%", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


@dataclass
class TennisMatch:
    event_id: str
    player1: str
    player2: str
    tournament: str
    surface: str
    sets1: int
    sets2: int
    games1: int
    games2: int
    point1: str = ""
    point2: str = ""
    server: int = 0
    status: str = ""
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def set_no(self) -> int:
        return max(1, self.sets1 + self.sets2 + 1)

    @property
    def games_played(self) -> int:
        return self.games1 + self.games2


STAT_ALIASES = {
    "aces": ("aces", "ace"),
    "double_faults": ("double faults", "double fault"),
    "first_serve_pct": ("1st serve %", "first serve %", "1st serve percentage"),
    "first_serve_won_pct": ("1st serve points won", "first serve points won"),
    "second_serve_won_pct": ("2nd serve points won", "second serve points won"),
    "break_points_saved": ("break points saved",),
    "break_points_won": ("break points converted", "break points won"),
    "service_points_won": ("service points won",),
    "return_points_won": ("return points won",),
    "total_points_won": ("total points won",),
}


def _stat_name(chunk: str) -> str:
    parts = _fields(chunk)
    for key in ("SE", "SG", "SC", "SA", "SD"):
        value = str(parts.get(key) or "").strip()
        if value and not value.isdigit():
            return value.lower()
    return chunk.lower()


def parse_stats(body: str) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for chunk in body.split("~"):
        f = _fields(chunk)
        left = _number(f.get("SH"))
        right = _number(f.get("SI"))
        if left is None or right is None:
            continue
        label = _stat_name(chunk)
        for name, aliases in STAT_ALIASES.items():
            if any(alias in label for alias in aliases):
                out[name] = (left, right)
                break
    return out


def fetch_stats(event_id: str) -> dict[str, tuple[float, float]]:
    body = _feed(f"df_st_1_{event_id}")
    return parse_stats(body) if body else {}


def _surface(tournament: str) -> str:
    low = tournament.lower()
    for s in ("hard", "clay", "grass", "carpet"):
        if s in low:
            return s
    return ""


def parse_master(body: str) -> list[TennisMatch]:
    matches: list[TennisMatch] = []
    tournament = ""
    singles = True
    for chunk in body.split("~"):
        f = _fields(chunk)
        if "ZA" in f:
            tournament = (f.get("ZA") or "").strip()
            low = tournament.lower()
            singles = "doubles" not in low
            continue
        event_id = (f.get("AA") or "").strip()
        if not event_id or f.get("AB") != LIVE_STATUS or not singles:
            continue
        p1 = (f.get("AE") or "").strip()
        p2 = (f.get("AF") or "").strip()
        if not p1 or not p2:
            continue

        # In Flashscore tennis master rows AG/AH represent aggregate sets while
        # GRA/GRB are the live game score in the current set. We retain raw data
        # because Flashscore occasionally changes per-competition fields.
        sets1 = _as_int(f.get("AG"))
        sets2 = _as_int(f.get("AH"))
        games1 = _as_int(f.get("GRA"))
        games2 = _as_int(f.get("GRB"))
        point1 = str(f.get("ERA") or f.get("OA") or "")
        point2 = str(f.get("ERB") or f.get("OB") or "")
        server = _as_int(f.get("SERV") or f.get("KJ") or 0)
        matches.append(TennisMatch(
            event_id=event_id,
            player1=p1,
            player2=p2,
            tournament=tournament,
            surface=_surface(tournament),
            sets1=sets1,
            sets2=sets2,
            games1=games1,
            games2=games2,
            point1=point1,
            point2=point2,
            server=server,
            status=f"AB={f.get('AB')} AC={f.get('AC','')}",
            raw=f,
        ))
    return list({m.event_id: m for m in matches}.values())


def discover_live() -> list[TennisMatch]:
    for feed in TENNNIS_FEEDS:
        body = _feed(feed)
        if not body:
            continue
        rows = parse_master(body)
        if rows:
            logger.info("FLASHSCORE TENNIS LIVE feed=%s matches=%d", feed, len(rows))
            return rows
    logger.warning("FLASHSCORE TENNIS LIVE: no rows parsed")
    return []
