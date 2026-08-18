from types import SimpleNamespace

import tennis_core


def test_game_hold_probability_is_monotonic():
    assert tennis_core.game_hold_probability(0.65) > tennis_core.game_hold_probability(0.55)


def test_projection_sums_to_one():
    result = tennis_core.project_set(2, 2, 0.78, 0.72, 1)
    assert 0 <= result["p1"] <= 1
    assert abs(result["p1"] + result["p2"] - 1.0) < 1e-9
    assert abs(sum(result["totals"].values()) - 1.0) < 1e-9


def test_late_set_is_blocked_by_early_gate():
    match = SimpleNamespace(games_played=6, games1=3, games2=3, server=1, tournament="ATP Test")
    assert tennis_core.analyse(match, {}, {"p1": 1.8, "p2": 2.0, "totals": {9.5: 1.8}}) == []


def test_analyse_requires_bookmaker_value():
    match = SimpleNamespace(games_played=3, games1=2, games2=1, server=1, tournament="ATP Test")
    # No 1xBet market = no betting signal even if the model has a preference.
    assert tennis_core.analyse(match, {}, {"p1": None, "p2": None, "totals": {}}) == []
