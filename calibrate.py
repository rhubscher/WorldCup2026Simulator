"""
Calibrate Poisson goal parameters from actual 2026 World Cup group results.

Loads completed group matches from data/scores.csv and pre-tournament ratings
from data/ratings.csv, then fits _BASE_LAMBDA and _K via maximum likelihood.
Prints diagnostics and recommended values to update in src/match.py.

Usage:
    uv run calibrate.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from src.data import load_ratings, load_scores
from src.ratings import get_probabilities

_RATINGS_PATH = "data/ratings.csv"
_SCORES_PATH = "data/scores.csv"

# Current values in src/match.py (for comparison)
_CURRENT_BASE_LAMBDA = 1.3
_CURRENT_K = 1.0


@dataclass
class MatchRecord:
    team_a: str
    team_b: str
    p_win_a: float
    p_draw: float
    goals_a: int
    goals_b: int


def _lambdas(p_win_a: float, p_draw: float, base_lambda: float, k: float) -> tuple[float, float]:
    p_win_b = 1.0 - p_win_a - p_draw
    la = base_lambda * (1.0 + k * (p_win_a - 0.5))
    lb = base_lambda * (1.0 + k * (p_win_b - 0.5))
    return max(0.01, la), max(0.01, lb)


def build_records(ratings_path: str = _RATINGS_PATH, scores_path: str = _SCORES_PATH) -> list[MatchRecord]:
    """Return one MatchRecord per completed group match (no shootouts)."""
    # Use pre-tournament ratings — no update_ratings() call, consistent with
    # how run_simulations() initializes before simulating remaining group games.
    ratings = load_ratings(ratings_path)
    scores = load_scores(scores_path)

    records = []
    for m in scores:
        if m.phase != "group":
            continue
        if m.penalties_a is not None:
            continue  # guard: shootout goals would be folded into goals_a/b
        p_win_a, p_draw, _ = get_probabilities(ratings[m.team_a], ratings[m.team_b])
        records.append(MatchRecord(
            team_a=m.team_a,
            team_b=m.team_b,
            p_win_a=p_win_a,
            p_draw=p_draw,
            goals_a=m.goals_a,
            goals_b=m.goals_b,
        ))
    return records


def print_goal_stats(records: list[MatchRecord]) -> None:
    all_goals = [r.goals_a for r in records] + [r.goals_b for r in records]
    n_matches = len(records)
    n_goals = sum(all_goals)
    mean = np.mean(all_goals)
    var = np.var(all_goals)

    print("=" * 60)
    print("ACTUAL GOAL STATISTICS")
    print("=" * 60)
    print(f"  Completed group matches : {n_matches}")
    print(f"  Total goals             : {n_goals}")
    print(f"  Goals per match         : {n_goals / n_matches:.3f}")
    print(f"  Goals per team-game     : {mean:.3f}")
    print(f"  Variance                : {var:.3f}")
    print(f"  Variance/mean ratio     : {var / mean:.3f}  (1.0 = pure Poisson)")
    print()
    print("  Goal distribution (per team-game):")
    max_show = 8
    counts = [0] * (max_show + 1)
    for g in all_goals:
        counts[min(g, max_show)] += 1
    n = len(all_goals)
    for k, c in enumerate(counts):
        bar = "█" * int(c / n * 40)
        label = f"{k}+" if k == max_show else str(k)
        print(f"    {label:>3} goals: {c:>3}  {c/n*100:>5.1f}%  {bar}")
    print()

    # Also print win/draw/loss counts from actual data
    wins = sum(1 for r in records if r.goals_a > r.goals_b)
    draws = sum(1 for r in records if r.goals_a == r.goals_b)
    losses = sum(1 for r in records if r.goals_a < r.goals_b)
    print(f"  Empirical W/D/L rates   : {wins/n_matches:.1%} / {draws/n_matches:.1%} / {losses/n_matches:.1%}")
    print()


def _poisson_log_pmf(k: int, lam: float) -> float:
    return k * math.log(lam) - lam - math.lgamma(k + 1)


def negative_log_likelihood(params: tuple[float, float], records: list[MatchRecord]) -> float:
    base_lambda, k = params
    if base_lambda <= 0 or k < 0:
        return 1e9
    nll = 0.0
    for r in records:
        la, lb = _lambdas(r.p_win_a, r.p_draw, base_lambda, k)
        nll -= _poisson_log_pmf(r.goals_a, la)
        nll -= _poisson_log_pmf(r.goals_b, lb)
    return nll


def fit_parameters(records: list[MatchRecord]) -> tuple[float, float]:
    """Fit (BASE_LAMBDA, K) via MLE with L-BFGS-B. Runs two starts to confirm stability."""
    bounds = [(0.5, 4.0), (0.0, 3.0)]
    best = None
    for x0 in ([_CURRENT_BASE_LAMBDA, _CURRENT_K], [1.0, 0.5], [2.0, 1.5]):
        result = minimize(
            negative_log_likelihood,
            x0=x0,
            args=(records,),
            method="L-BFGS-B",
            bounds=bounds,
        )
        if best is None or result.fun < best.fun:
            best = result
    return float(best.x[0]), float(best.x[1])


def print_fit_diagnostics(
    records: list[MatchRecord],
    fitted_base: float,
    fitted_k: float,
) -> None:
    current_nll = negative_log_likelihood((_CURRENT_BASE_LAMBDA, _CURRENT_K), records)
    fitted_nll = negative_log_likelihood((fitted_base, fitted_k), records)

    print("=" * 60)
    print("FIT RESULTS")
    print("=" * 60)
    print(f"  Current  (base={_CURRENT_BASE_LAMBDA:.3f}, k={_CURRENT_K:.3f}): NLL = {current_nll:.2f}")
    print(f"  Fitted   (base={fitted_base:.3f}, k={fitted_k:.3f}): NLL = {fitted_nll:.2f}")
    print(f"  Log-likelihood improvement: {current_nll - fitted_nll:.2f}")
    if fitted_k < 0.1:
        print("  WARNING: fitted k is very small — win probability has little effect on lambdas")
    print()

    # PMF comparison table
    all_goals = [r.goals_a for r in records] + [r.goals_b for r in records]
    n = len(all_goals)
    empirical = [sum(1 for g in all_goals if g == k) / n for k in range(7)]
    empirical.append(sum(1 for g in all_goals if g >= 7) / n)

    # Average lambdas across all records for a summary PMF
    avg_la_current = np.mean([_lambdas(r.p_win_a, r.p_draw, _CURRENT_BASE_LAMBDA, _CURRENT_K)[0] for r in records])
    avg_lb_current = np.mean([_lambdas(r.p_win_a, r.p_draw, _CURRENT_BASE_LAMBDA, _CURRENT_K)[1] for r in records])
    avg_lam_current = (avg_la_current + avg_lb_current) / 2

    avg_la_fitted = np.mean([_lambdas(r.p_win_a, r.p_draw, fitted_base, fitted_k)[0] for r in records])
    avg_lb_fitted = np.mean([_lambdas(r.p_win_a, r.p_draw, fitted_base, fitted_k)[1] for r in records])
    avg_lam_fitted = (avg_la_fitted + avg_lb_fitted) / 2

    def poisson_pmf(k, lam):
        return math.exp(_poisson_log_pmf(k, lam))

    print(f"  Goal distribution comparison (per team-game):")
    print(f"  {'Goals':>5}  {'Empirical':>9}  {'Current':>9}  {'Fitted':>9}")
    print(f"  {'-'*5}  {'-'*9}  {'-'*9}  {'-'*9}")
    for k in range(7):
        emp = empirical[k]
        cur = poisson_pmf(k, avg_lam_current)
        fit = poisson_pmf(k, avg_lam_fitted)
        print(f"  {k:>5}  {emp*100:>8.1f}%  {cur*100:>8.1f}%  {fit*100:>8.1f}%")
    # 7+
    emp7 = empirical[7]
    cur7 = 1 - sum(poisson_pmf(k, avg_lam_current) for k in range(7))
    fit7 = 1 - sum(poisson_pmf(k, avg_lam_fitted) for k in range(7))
    print(f"  {'7+':>5}  {emp7*100:>8.1f}%  {cur7*100:>8.1f}%  {fit7*100:>8.1f}%")
    print()
    print(f"  Avg lambda (current): {avg_lam_current:.3f}")
    print(f"  Avg lambda (fitted) : {avg_lam_fitted:.3f}")
    print()

    # Implied W/D/L from direct Poisson sampling with fitted params (Monte Carlo)
    rng = np.random.default_rng(42)
    avg_p_win = np.mean([r.p_win_a for r in records])
    avg_p_draw = np.mean([r.p_draw for r in records])
    avg_p_loss = 1.0 - avg_p_win - avg_p_draw
    la, lb = _lambdas(avg_p_win, avg_p_draw, fitted_base, fitted_k)
    n_sim = 100_000
    ga_sim = rng.poisson(la, n_sim)
    gb_sim = rng.poisson(lb, n_sim)
    sim_win = np.mean(ga_sim > gb_sim)
    sim_draw = np.mean(ga_sim == gb_sim)
    sim_loss = np.mean(ga_sim < gb_sim)
    print(f"  Implied W/D/L from direct Poisson sampling (avg p_win={avg_p_win:.2f}):")
    print(f"    Glicko-2 target : {avg_p_win:.1%} / {avg_p_draw:.1%} / {avg_p_loss:.1%}")
    print(f"    Simulated       : {sim_win:.1%} / {sim_draw:.1%} / {sim_loss:.1%}")
    print()


def main() -> None:
    records = build_records()
    if not records:
        print("No completed group matches found — nothing to calibrate.")
        return

    print_goal_stats(records)

    print("Fitting parameters via MLE...")
    fitted_base, fitted_k = fit_parameters(records)

    print_fit_diagnostics(records, fitted_base, fitted_k)

    print("=" * 60)
    print("RECOMMENDATION — update src/match.py:")
    print("=" * 60)
    print(f"  _BASE_LAMBDA = {fitted_base:.4f}  # was {_CURRENT_BASE_LAMBDA} (fitted from {len(records)} matches)")
    print(f"  _K           = {fitted_k:.4f}  # was {_CURRENT_K}")
    print()


if __name__ == "__main__":
    main()
