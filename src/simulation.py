from __future__ import annotations

import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from itertools import combinations

from .bracket import _QF_PAIRS, _R16_PAIRS, _SF_PAIRS, build_r32_bracket
from .data import GROUPS, MatchResult, TeamRating, TEAM_TO_GROUP
from .match import simulate_group_match, simulate_knockout_match, simulate_knockout_match_result
from .ratings import get_probabilities, update_ratings
from .tournament import qualify_from_groups, rank_third_place

ROUNDS = ["r32", "r16", "qf", "sf", "final", "win"]
_PARALLEL_THRESHOLD = 2_000

_ProbCache = dict[tuple[str, str], tuple[float, float, float]]


def _make_count_dict() -> defaultdict:
    return defaultdict(int)


@dataclass
class SimResults:
    n: int
    win_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    round_counts: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(_make_count_dict)
    )
    group_pos_counts: dict[str, list[int]] = field(
        default_factory=dict
    )  # team → [1st, 2nd, 3rd, 4th]
    goals_for: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(_make_count_dict)
    )  # team → phase → cumulative goals across all n simulations
    phase_goals: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )  # phase → cumulative goals (all teams) across all n simulations
    goals_against: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(_make_count_dict)
    )  # team → phase → cumulative goals conceded across all n simulations
    def __post_init__(self):
        all_teams = [t for teams in GROUPS.values() for t in teams]
        for team in all_teams:
            self.group_pos_counts.setdefault(team, [0, 0, 0, 0])


def _build_prob_cache(ratings: dict[str, TeamRating]) -> _ProbCache:
    cache: _ProbCache = {}
    teams = list(ratings)
    for a, b in combinations(teams, 2):
        p_win, p_draw, p_loss = get_probabilities(ratings[a], ratings[b])
        cache[(a, b)] = (p_win, p_draw, p_loss)
        cache[(b, a)] = (p_loss, p_draw, p_win)
    return cache


def _merge_results(target: SimResults, source: SimResults) -> None:
    for team, count in source.win_counts.items():
        target.win_counts[team] += count
    for team, rounds in source.round_counts.items():
        for round_name, count in rounds.items():
            target.round_counts[team][round_name] += count
    for team, positions in source.group_pos_counts.items():
        for i, count in enumerate(positions):
            target.group_pos_counts[team][i] += count
    for team, phases in source.goals_for.items():
        for phase, count in phases.items():
            target.goals_for[team][phase] += count
    for phase, count in source.phase_goals.items():
        target.phase_goals[phase] += count
    for team, phases in source.goals_against.items():
        for phase, count in phases.items():
            target.goals_against[team][phase] += count


def _run_batch(
    ratings: dict[str, TeamRating],
    completed: list[MatchResult],
    n: int,
) -> SimResults:
    results = SimResults(n=n)
    for _ in range(n):
        _simulate_once(ratings, completed, results)
    return results


def _group_results_from_completed(completed: list[MatchResult]) -> dict[str, list[MatchResult]]:
    group_results: dict[str, list[MatchResult]] = {g: [] for g in GROUPS}
    for r in completed:
        if r.phase == "group" and r.group in GROUPS:
            group_results[r.group].append(r)
    return group_results


def _pending_group_matches(
    group_results: dict[str, list[MatchResult]],
) -> dict[str, list[tuple[str, str]]]:
    """Return unplayed matches per group as (team_a, team_b) pairs."""
    pending: dict[str, list[tuple[str, str]]] = {}
    for group, teams in GROUPS.items():
        played = {
            frozenset([r.team_a, r.team_b])
            for r in group_results[group]
        }
        pending[group] = [
            (a, b)
            for a, b in combinations(teams, 2)
            if frozenset([a, b]) not in played
        ]
    return pending


def _sim_knockout_round(
    matchups: list[tuple[str, str]],
    prob_cache: _ProbCache,
    results: SimResults,
    round_name: str,
) -> list[str]:
    winners = []
    for team_a, team_b in matchups:
        winner = simulate_knockout_match(team_a, team_b, prob_cache)
        results.round_counts[winner][round_name] += 1
        winners.append(winner)
    return winners


def _pairs(teams: list[str]) -> list[tuple[str, str]]:
    return [(teams[i], teams[i + 1]) for i in range(0, len(teams), 2)]


def _simulate_once(
    ratings: dict[str, TeamRating],
    completed: list[MatchResult],
    results: SimResults,
) -> None:
    prob_cache = _build_prob_cache(ratings)

    # --- Group phase ---
    group_results = _group_results_from_completed(completed)
    pending = _pending_group_matches(group_results)

    for group, matches in pending.items():
        for team_a, team_b in matches:
            ga, gb = simulate_group_match(team_a, team_b, prob_cache)
            group_results[group].append(
                MatchResult(
                    phase="group",
                    group=group,
                    team_a=team_a,
                    team_b=team_b,
                    goals_a=ga,
                    goals_b=gb,
                    aet=False,
                    penalties_a=None,
                    penalties_b=None,
                )
            )

    winners, runners_up, thirds = qualify_from_groups(group_results)
    best_8 = rank_third_place(thirds)

    for group_matches in group_results.values():
        for mr in group_matches:
            results.goals_for[mr.team_a]["group"] += mr.goals_a
            results.goals_for[mr.team_b]["group"] += mr.goals_b
            results.goals_against[mr.team_a]["group"] += mr.goals_b
            results.goals_against[mr.team_b]["group"] += mr.goals_a
            results.phase_goals["group"] += mr.goals_a + mr.goals_b

    # Record group positions
    from .tournament import rank_group
    for group, teams in GROUPS.items():
        ranked = rank_group(group_results[group], teams)
        for pos, ts in enumerate(ranked):
            results.group_pos_counts[ts.team][pos] += 1

    all_group_matches = [m for ms in group_results.values() for m in ms]
    ratings = update_ratings(ratings, all_group_matches)
    prob_cache = _build_prob_cache(ratings)

    # --- Round of 32: all 32 qualifiers "reach" r32 ---
    r32_matchups = build_r32_bracket(winners, runners_up, best_8)

    r32_winners = []
    r32_match_results: list[MatchResult] = []
    for team_a, team_b in r32_matchups:
        results.round_counts[team_a]["r32"] += 1
        results.round_counts[team_b]["r32"] += 1
        mr = simulate_knockout_match_result(team_a, team_b, prob_cache, "r32")
        winner = mr.winner()
        results.round_counts[winner]["r16"] += 1
        results.goals_for[team_a]["r32"] += mr.goals_a
        results.goals_for[team_b]["r32"] += mr.goals_b
        results.goals_against[team_a]["r32"] += mr.goals_b
        results.goals_against[team_b]["r32"] += mr.goals_a
        results.phase_goals["r32"] += mr.goals_a + mr.goals_b
        r32_winners.append(winner)
        r32_match_results.append(mr)

    ratings = update_ratings(ratings, r32_match_results)
    prob_cache = _build_prob_cache(ratings)

    # --- Round of 16 ---
    r16_matchups = [(r32_winners[a], r32_winners[b]) for a, b in _R16_PAIRS]
    r16_winners = []
    r16_match_results: list[MatchResult] = []
    for team_a, team_b in r16_matchups:
        mr = simulate_knockout_match_result(team_a, team_b, prob_cache, "r16")
        winner = mr.winner()
        results.round_counts[winner]["qf"] += 1
        results.goals_for[team_a]["r16"] += mr.goals_a
        results.goals_for[team_b]["r16"] += mr.goals_b
        results.goals_against[team_a]["r16"] += mr.goals_b
        results.goals_against[team_b]["r16"] += mr.goals_a
        results.phase_goals["r16"] += mr.goals_a + mr.goals_b
        r16_winners.append(winner)
        r16_match_results.append(mr)

    ratings = update_ratings(ratings, r16_match_results)
    prob_cache = _build_prob_cache(ratings)

    # --- Quarterfinals ---
    qf_matchups = [(r16_winners[a], r16_winners[b]) for a, b in _QF_PAIRS]
    qf_winners = []
    qf_match_results: list[MatchResult] = []
    for team_a, team_b in qf_matchups:
        mr = simulate_knockout_match_result(team_a, team_b, prob_cache, "qf")
        winner = mr.winner()
        results.round_counts[winner]["sf"] += 1
        results.goals_for[team_a]["qf"] += mr.goals_a
        results.goals_for[team_b]["qf"] += mr.goals_b
        results.goals_against[team_a]["qf"] += mr.goals_b
        results.goals_against[team_b]["qf"] += mr.goals_a
        results.phase_goals["qf"] += mr.goals_a + mr.goals_b
        qf_winners.append(winner)
        qf_match_results.append(mr)

    ratings = update_ratings(ratings, qf_match_results)
    prob_cache = _build_prob_cache(ratings)

    # --- Semifinals ---
    sf_matchups = [(qf_winners[a], qf_winners[b]) for a, b in _SF_PAIRS]
    sf_winners = []
    sf_match_results: list[MatchResult] = []
    for team_a, team_b in sf_matchups:
        mr = simulate_knockout_match_result(team_a, team_b, prob_cache, "sf")
        winner = mr.winner()
        results.round_counts[winner]["final"] += 1
        results.goals_for[team_a]["sf"] += mr.goals_a
        results.goals_for[team_b]["sf"] += mr.goals_b
        results.goals_against[team_a]["sf"] += mr.goals_b
        results.goals_against[team_b]["sf"] += mr.goals_a
        results.phase_goals["sf"] += mr.goals_a + mr.goals_b
        sf_winners.append(winner)
        sf_match_results.append(mr)

    ratings = update_ratings(ratings, sf_match_results)
    prob_cache = _build_prob_cache(ratings)

    # --- Final ---
    mr = simulate_knockout_match_result(sf_winners[0], sf_winners[1], prob_cache, "final")
    champion = mr.winner()
    results.goals_for[sf_winners[0]]["final"] += mr.goals_a
    results.goals_for[sf_winners[1]]["final"] += mr.goals_b
    results.goals_against[sf_winners[0]]["final"] += mr.goals_b
    results.goals_against[sf_winners[1]]["final"] += mr.goals_a
    results.phase_goals["final"] += mr.goals_a + mr.goals_b
    results.win_counts[champion] += 1


def trace_team(
    ratings: dict[str, TeamRating],
    completed: list[MatchResult],
    team: str,
) -> list[MatchResult]:
    """Run one simulation and return every match involving *team* with full scorelines."""
    updated = update_ratings(ratings, completed)
    prob_cache = _build_prob_cache(updated)

    # Group phase
    group_results = _group_results_from_completed(completed)
    pending = _pending_group_matches(group_results)
    for group, matches in pending.items():
        for team_a, team_b in matches:
            ga, gb = simulate_group_match(team_a, team_b, prob_cache)
            group_results[group].append(
                MatchResult(
                    phase="group", group=group,
                    team_a=team_a, team_b=team_b,
                    goals_a=ga, goals_b=gb,
                    aet=False, penalties_a=None, penalties_b=None,
                )
            )

    winners, runners_up, thirds = qualify_from_groups(group_results)
    best_8 = rank_third_place(thirds)
    r32_matchups = build_r32_bracket(winners, runners_up, best_8)

    updated = update_ratings(updated, [m for ms in group_results.values() for m in ms])
    prob_cache = _build_prob_cache(updated)

    ko_matches: list[MatchResult] = []

    r32_winners: list[str] = []
    r32_results: list[MatchResult] = []
    for ta, tb in r32_matchups:
        mr = simulate_knockout_match_result(ta, tb, prob_cache, "r32")
        ko_matches.append(mr)
        r32_winners.append(mr.winner())
        r32_results.append(mr)

    updated = update_ratings(updated, r32_results)
    prob_cache = _build_prob_cache(updated)

    r16_matchups = [(r32_winners[a], r32_winners[b]) for a, b in _R16_PAIRS]
    r16_winners: list[str] = []
    r16_results: list[MatchResult] = []
    for ta, tb in r16_matchups:
        mr = simulate_knockout_match_result(ta, tb, prob_cache, "r16")
        ko_matches.append(mr)
        r16_winners.append(mr.winner())
        r16_results.append(mr)

    updated = update_ratings(updated, r16_results)
    prob_cache = _build_prob_cache(updated)

    qf_matchups = [(r16_winners[a], r16_winners[b]) for a, b in _QF_PAIRS]
    qf_winners: list[str] = []
    qf_results: list[MatchResult] = []
    for ta, tb in qf_matchups:
        mr = simulate_knockout_match_result(ta, tb, prob_cache, "qf")
        ko_matches.append(mr)
        qf_winners.append(mr.winner())
        qf_results.append(mr)

    updated = update_ratings(updated, qf_results)
    prob_cache = _build_prob_cache(updated)

    sf_matchups = [(qf_winners[a], qf_winners[b]) for a, b in _SF_PAIRS]
    sf_winners: list[str] = []
    sf_results: list[MatchResult] = []
    for ta, tb in sf_matchups:
        mr = simulate_knockout_match_result(ta, tb, prob_cache, "sf")
        ko_matches.append(mr)
        sf_winners.append(mr.winner())
        sf_results.append(mr)

    updated = update_ratings(updated, sf_results)
    prob_cache = _build_prob_cache(updated)

    mr = simulate_knockout_match_result(sf_winners[0], sf_winners[1], prob_cache, "final")
    ko_matches.append(mr)

    all_matches = [m for ms in group_results.values() for m in ms] + ko_matches
    return [m for m in all_matches if m.team_a == team or m.team_b == team]


def run_simulations(
    ratings: dict[str, TeamRating],
    completed: list[MatchResult],
    n: int,
) -> SimResults:
    updated_ratings = update_ratings(ratings, completed)

    workers = os.cpu_count() or 1
    if n < _PARALLEL_THRESHOLD or workers <= 1:
        results = SimResults(n=n)
        for _ in range(n):
            _simulate_once(updated_ratings, completed, results)
        return results

    workers = min(workers, n)
    batch_sizes = [n // workers] * workers
    for i in range(n % workers):
        batch_sizes[i] += 1

    results = SimResults(n=n)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_run_batch, updated_ratings, completed, b)
            for b in batch_sizes
        ]
        for future in futures:
            _merge_results(results, future.result())

    return results
