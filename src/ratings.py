from __future__ import annotations

import math
from collections import defaultdict

from glicko2.glicko2 import Player

from .data import MatchResult, TeamRating

_SCALE = 173.7178
_BASE_DRAW_RATE = 0.28


def _to_player(tr: TeamRating) -> Player:
    return Player(rating=tr.rating, rd=tr.rd, vol=tr.volatility)


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi**2 / math.pi**2)


def _expected_score(mu_a: float, mu_b: float, phi_b: float) -> float:
    """Glicko-2 E function — expected score for A against B (internal scale)."""
    return 1.0 / (1.0 + math.exp(-_g(phi_b) * (mu_a - mu_b)))


def get_probabilities(a: TeamRating, b: TeamRating) -> tuple[float, float, float]:
    """Return (p_win_a, p_draw, p_loss_a) for team A vs team B."""
    mu_a = (a.rating - 1500.0) / _SCALE
    mu_b = (b.rating - 1500.0) / _SCALE
    phi_b = b.rd / _SCALE

    e = _expected_score(mu_a, mu_b, phi_b)

    p_draw = _BASE_DRAW_RATE * (1.0 - abs(2.0 * e - 1.0))
    p_win = e - 0.5 * p_draw
    p_loss = (1.0 - e) - 0.5 * p_draw

    # Clamp to [0, 1] to guard against floating-point edge cases
    p_win = max(0.0, p_win)
    p_loss = max(0.0, p_loss)
    p_draw = max(0.0, 1.0 - p_win - p_loss)

    total = p_win + p_draw + p_loss
    return p_win / total, p_draw / total, p_loss / total


def update_ratings(
    ratings: dict[str, TeamRating],
    results: list[MatchResult],
) -> dict[str, TeamRating]:
    """Return updated ratings after processing completed match results.

    All results are treated as a single Glicko-2 rating period.
    """
    # Collect each team's opponents and outcomes for this period
    opponents: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    # value: (opp_rating, opp_rd, outcome)  outcome: 1=win, 0.5=draw, 0=loss

    for r in results:
        ra = ratings[r.team_a]
        rb = ratings[r.team_b]
        if r.is_draw():
            outcome_a, outcome_b = 0.5, 0.5
        elif r.winner() == r.team_a:
            outcome_a, outcome_b = 1.0, 0.0
        else:
            outcome_a, outcome_b = 0.0, 1.0
        opponents[r.team_a].append((rb.rating, rb.rd, outcome_a))
        opponents[r.team_b].append((ra.rating, ra.rd, outcome_b))

    updated: dict[str, TeamRating] = {}
    for team, tr in ratings.items():
        player = _to_player(tr)
        games = opponents.get(team, [])
        if games:
            opp_ratings = [g[0] for g in games]
            opp_rds = [g[1] for g in games]
            outcomes = [g[2] for g in games]
            player.update_player(opp_ratings, opp_rds, outcomes)
        else:
            player.did_not_compete()
        updated[team] = TeamRating(
            team=team,
            rating=player.getRating(),
            rd=player.getRd(),
            volatility=player.vol,
        )

    return updated
