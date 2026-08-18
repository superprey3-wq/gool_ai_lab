"""GOOL TENNIS probability engine.

Two outputs only:
- SET WINNER CORE: player 1 / player 2 to win the current set
- SET TOTAL CORE: over games in the current set

The model estimates each player's hold probability from Flashscore serve stats,
then solves the remaining set as a small probability tree. This makes the score,
who serves next and current service quality matter directly.
"""
from __future__ import annotations

from functools import lru_cache
import math
import os
from typing import Any

EARLY_MIN_GAMES = int(os.getenv("TENNIS_EARLY_MIN_GAMES", "2"))
EARLY_MAX_GAMES = int(os.getenv("TENNIS_EARLY_MAX_GAMES", "5"))
MIN_PROB = float(os.getenv("TENNIS_MIN_PROB", "0.67"))
MIN_EDGE = float(os.getenv("TENNIS_MIN_EDGE", "0.055"))
MIN_ODD = float(os.getenv("TENNIS_MIN_ODD", "1.35"))
MAX_ODD = float(os.getenv("TENNIS_MAX_ODD", "2.60"))


def _pair(stats: dict[str, tuple[float, float]], key: str, default: tuple[float, float]) -> tuple[float, float]:
    value = stats.get(key)
    if not value:
        return default
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError, IndexError):
        return default


def _pct(value: float, fallback: float) -> float:
    if value <= 0:
        return fallback
    return max(0.25, min(0.90, value / 100.0 if value > 1 else value))


def game_hold_probability(point_win: float) -> float:
    """Exact probability of winning a standard advantage game from 0-0."""
    p = max(0.35, min(0.85, point_win))
    q = 1.0 - p
    before_deuce = p**4 * (1 + 4*q + 10*q*q)
    reach_deuce = 20 * p**3 * q**3
    win_from_deuce = (p*p) / max(1e-9, 1 - 2*p*q)
    return max(0.30, min(0.95, before_deuce + reach_deuce * win_from_deuce))


def estimate_holds(stats: dict[str, tuple[float, float]], is_wta: bool = False) -> tuple[float, float]:
    base_point = 0.60 if is_wta else 0.62
    fs = _pair(stats, "first_serve_pct", (62.0, 62.0))
    fsw = _pair(stats, "first_serve_won_pct", (70.0, 70.0))
    ssw = _pair(stats, "second_serve_won_pct", (50.0, 50.0))
    dfs = _pair(stats, "double_faults", (0.0, 0.0))
    holds = []
    for i in range(2):
        first_in = _pct(fs[i], 0.62)
        first_won = _pct(fsw[i], 0.70)
        second_won = _pct(ssw[i], 0.50)
        point = first_in * first_won + (1-first_in) * second_won
        if not stats:
            point = base_point
        # A few double faults early are meaningful, but cap the correction.
        point -= min(0.025, max(0.0, dfs[i]) * 0.004)
        point = 0.70 * point + 0.30 * base_point
        holds.append(game_hold_probability(point))
    return holds[0], holds[1]


def _terminal(a: int, b: int) -> int:
    if (a >= 6 or b >= 6) and abs(a-b) >= 2:
        return 1 if a > b else 2
    if a == 7 and b == 6:
        return 1
    if b == 7 and a == 6:
        return 2
    return 0


def project_set(games1: int, games2: int, hold1: float, hold2: float, next_server: int = 0) -> dict[str, Any]:
    """Return P1/P2 set win probabilities and final-games distribution.

    If the server is unknown, both possible next servers are averaged 50/50.
    Tie-break at 6-6 is approximated from relative service strength.
    """
    games1, games2 = max(0, games1), max(0, games2)

    def solve(start_server: int):
        @lru_cache(maxsize=None)
        def rec(a: int, b: int, server: int):
            winner = _terminal(a, b)
            if winner:
                total = a + b
                return (1.0 if winner == 1 else 0.0, {total: 1.0})
            if a == 6 and b == 6:
                # Relative serve quality drives a restrained tie-break edge.
                edge = (hold1 - hold2) * 0.75
                p1 = max(0.30, min(0.70, 0.5 + edge))
                return p1, {13: 1.0}
            p_game1 = hold1 if server == 1 else (1.0 - hold2)
            p_game1 = max(0.08, min(0.92, p_game1))
            p1a, dist_a = rec(a + 1, b, 2 if server == 1 else 1)
            p1b, dist_b = rec(a, b + 1, 2 if server == 1 else 1)
            dist: dict[int, float] = {}
            for total, prob in dist_a.items():
                dist[total] = dist.get(total, 0.0) + p_game1 * prob
            for total, prob in dist_b.items():
                dist[total] = dist.get(total, 0.0) + (1-p_game1) * prob
            return p_game1*p1a + (1-p_game1)*p1b, dist
        return rec(games1, games2, start_server)

    if next_server in (1, 2):
        p1, dist = solve(next_server)
    else:
        p1a, da = solve(1)
        p1b, db = solve(2)
        p1 = (p1a + p1b) / 2
        dist = {}
        for k in set(da) | set(db):
            dist[k] = (da.get(k, 0.0) + db.get(k, 0.0)) / 2
    return {"p1": p1, "p2": 1-p1, "totals": dist}


def over_probability(distribution: dict[int, float], line: float) -> float:
    return sum(prob for games, prob in distribution.items() if games > line)


def fair_probability_from_odds(odd: float | None) -> float | None:
    try:
        o = float(odd)
        return 1.0 / o if o > 1.0 else None
    except (TypeError, ValueError):
        return None


def _value(prob: float, odd: float | None) -> tuple[float, float | None]:
    market = fair_probability_from_odds(odd)
    return prob - market if market is not None else 0.0, market


def analyse(match, stats: dict[str, tuple[float, float]], odds: dict[str, Any]) -> list[dict[str, Any]]:
    if match.games_played < EARLY_MIN_GAMES or match.games_played > EARLY_MAX_GAMES:
        return []
    is_wta = "wta" in (match.tournament or "").lower() or "women" in (match.tournament or "").lower()
    hold1, hold2 = estimate_holds(stats, is_wta=is_wta)
    projection = project_set(match.games1, match.games2, hold1, hold2, match.server)
    candidates: list[dict[str, Any]] = []

    for side in (1, 2):
        prob = projection[f"p{side}"]
        odd = odds.get(f"p{side}")
        edge, market = _value(prob, odd)
        if prob >= MIN_PROB and odd is not None and MIN_ODD <= float(odd) <= MAX_ODD and edge >= MIN_EDGE:
            candidates.append({
                "core": "SET_WINNER_CORE", "pick": f"P{side}", "line": None,
                "probability": prob, "odd": float(odd), "market_probability": market,
                "edge": edge, "hold1": hold1, "hold2": hold2,
            })

    for line, odd in (odds.get("totals") or {}).items():
        try:
            line, odd = float(line), float(odd)
        except (TypeError, ValueError):
            continue
        if line not in (8.5, 9.5, 10.5, 11.5, 12.5) or not (MIN_ODD <= odd <= MAX_ODD):
            continue
        prob = over_probability(projection["totals"], line)
        edge, market = _value(prob, odd)
        if prob >= MIN_PROB and edge >= MIN_EDGE:
            candidates.append({
                "core": "SET_TOTAL_CORE", "pick": "OVER", "line": line,
                "probability": prob, "odd": odd, "market_probability": market,
                "edge": edge, "hold1": hold1, "hold2": hold2,
            })

    # Only the strongest value signal from a match/set is sent.
    candidates.sort(key=lambda x: (x["edge"], x["probability"]), reverse=True)
    return candidates[:1]
