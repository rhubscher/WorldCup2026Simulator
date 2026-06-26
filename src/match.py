from __future__ import annotations

import math
import random

import numpy as np

from .data import MatchResult

# Fitted via MLE on 54 completed 2026 WC group matches (calibrate.py).
# Previous values: _BASE_LAMBDA = 1.3, _K = 1.0 — underestimated high-scoring games.
_BASE_LAMBDA = 1.7348
_K = 1.8802

_ProbCache = dict[tuple[str, str], tuple[float, float, float]]


def _lambdas(p_win_a: float, p_draw: float) -> tuple[float, float]:
    p_win_b = 1.0 - p_win_a - p_draw
    la = _BASE_LAMBDA * (1.0 + _K * (p_win_a - 0.5))
    lb = _BASE_LAMBDA * (1.0 + _K * (p_win_b - 0.5))
    return max(0.01, la), max(0.01, lb)


def simulate_group_match(
    team_a: str,
    team_b: str,
    probs: _ProbCache,
) -> tuple[int, int]:
    """Simulate a group-phase match; returns (goals_a, goals_b)."""
    p_win, p_draw, p_loss = probs[(team_a, team_b)]
    la, lb = _lambdas(p_win, p_draw)
    return int(np.random.poisson(la)), int(np.random.poisson(lb))


def simulate_knockout_match(
    team_a: str,
    team_b: str,
    probs: _ProbCache,
) -> str:
    """Simulate a knockout match; returns the winning team name."""
    p_win, p_draw, p_loss = probs[(team_a, team_b)]
    outcome = np.random.choice(["win", "draw", "loss"], p=[p_win, p_draw, p_loss])

    if outcome == "win":
        return team_a
    if outcome == "loss":
        return team_b

    # Draw after 90 min → extra time (same probabilities)
    outcome_aet = np.random.choice(["win", "draw", "loss"], p=[p_win, p_draw, p_loss])
    if outcome_aet == "win":
        return team_a
    if outcome_aet == "loss":
        return team_b

    # Still level → penalty shootout (50/50)
    return random.choice([team_a, team_b])


def _simulate_penalties() -> tuple[int, int]:
    p = 0.75
    pa, pb = 0, 0
    for r in range(1, 6):
        pa += int(random.random() < p)
        # After A's kick r: A has taken r, B has taken r-1; remaining A=5-r, B=6-r
        if pa > pb + (6 - r) or pb > pa + (5 - r):
            return pa, pb
        pb += int(random.random() < p)
        # After B's kick r: both taken r; remaining 5-r each
        if pa > pb + (5 - r) or pb > pa + (5 - r):
            return pa, pb
    # Sudden death: continue until one team leads after a complete round
    while pa == pb:
        pa += int(random.random() < p)
        pb += int(random.random() < p)
    return pa, pb


def simulate_knockout_match_result(
    team_a: str,
    team_b: str,
    probs: _ProbCache,
    phase: str,
) -> MatchResult:
    """Simulate a knockout match with full scoreline; returns a MatchResult."""
    p_win, p_draw, p_loss = probs[(team_a, team_b)]
    la, lb = _lambdas(p_win, p_draw)

    ga = int(np.random.poisson(la))
    gb = int(np.random.poisson(lb))

    if ga != gb:
        return MatchResult(phase, "", team_a, team_b, ga, gb, False, None, None)

    # Extra time (~30 min, λ scaled to 1/3)
    ga += int(np.random.poisson(la * 0.33))
    gb += int(np.random.poisson(lb * 0.33))

    if ga != gb:
        return MatchResult(phase, "", team_a, team_b, ga, gb, True, None, None)

    # Penalty shootout
    pa, pb = _simulate_penalties()
    return MatchResult(phase, "", team_a, team_b, ga + pa, gb + pb, True, pa, pb)


def score_distribution(
    team_a: str,
    team_b: str,
    probs: _ProbCache,
    max_goals: int = 8,
) -> np.ndarray:
    """Return a (max_goals+1)×(max_goals+1) probability matrix.

    matrix[i][j] = P(goals_a == i) * P(goals_b == j)
    where goals_a ~ Poisson(la), goals_b ~ Poisson(lb), independent.
    Rows index team_a goals; columns index team_b goals.
    """
    p_win, p_draw, p_loss = probs[(team_a, team_b)]
    la, lb = _lambdas(p_win, p_draw)
    size = max_goals + 1
    ks = np.arange(size)
    log_pmf_a = ks * math.log(la) - la - np.array([math.lgamma(k + 1) for k in ks])
    log_pmf_b = ks * math.log(lb) - lb - np.array([math.lgamma(k + 1) for k in ks])
    return np.outer(np.exp(log_pmf_a), np.exp(log_pmf_b))
