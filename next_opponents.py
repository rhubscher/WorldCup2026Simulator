"""
next_opponents.py — compute probable next-round opponents in the upcoming knockout round.

Usage:
  uv run next_opponents.py [-n 5000] [--team France]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.bracket import _QF_PAIRS, _R16_PAIRS, _SF_PAIRS, build_r32_bracket
from src.data import GROUPS, MatchResult, load_ratings, load_scores
from src.match import simulate_group_match, simulate_knockout_match_result
from src.ratings import update_ratings
from src.simulation import (
    _build_prob_cache,
    _group_results_from_completed,
    _pending_group_matches,
)
from src.tournament import qualify_from_groups, rank_third_place

_KO_ROUNDS = ["r32", "r16", "qf", "sf", "final"]
_ROUND_LABELS = {
    "r32": "Round of 32",
    "r16": "Round of 16",
    "qf": "Quarterfinals",
    "sf": "Semifinals",
    "final": "Final",
}
_EXPECTED_COUNTS = {"r32": 16, "r16": 8, "qf": 4, "sf": 2, "final": 1}


def _detect_target_round(completed: list[MatchResult]) -> str:
    """Return the current or next knockout round (first one with pending matches)."""
    for r in _KO_ROUNDS:
        n = sum(1 for m in completed if m.phase == r)
        if n < _EXPECTED_COUNTS[r]:
            return r
    return "final"


def _completed_ko(completed: list[MatchResult]) -> dict[str, dict[frozenset, str]]:
    """Build {phase: {frozenset({ta,tb}): winner}} for completed knockout matches."""
    ko: dict[str, dict[frozenset, str]] = {r: {} for r in _KO_ROUNDS}
    for m in completed:
        if m.phase in ko:
            ko[m.phase][frozenset({m.team_a, m.team_b})] = m.winner()
    return ko


def _sim_round(
    matchups: list[tuple[str, str]],
    done: dict[frozenset, str],
    prob_cache: dict,
    phase: str,
) -> tuple[list[str], list[MatchResult]]:
    """Simulate a knockout round; use known results where available.

    Returns (winners list, list of newly simulated MatchResults for rating updates).
    """
    winners: list[str] = []
    sim_results: list[MatchResult] = []
    for ta, tb in matchups:
        pair = frozenset({ta, tb})
        if pair in done:
            winners.append(done[pair])
        else:
            mr = simulate_knockout_match_result(ta, tb, prob_cache, phase)
            winners.append(mr.winner())
            sim_results.append(mr)
    return winners, sim_results


def _one_sim(
    ratings: dict,
    completed: list[MatchResult],
    ko_done: dict[str, dict[frozenset, str]],
    target_round: str,
    opponent_counts: dict,
    qual_counts: dict,
) -> None:
    prob_cache = _build_prob_cache(ratings)

    # Complete remaining group matches
    group_results = _group_results_from_completed(completed)
    for group, matches in _pending_group_matches(group_results).items():
        for ta, tb in matches:
            ga, gb = simulate_group_match(ta, tb, prob_cache)
            group_results[group].append(
                MatchResult(
                    phase="group",
                    group=group,
                    team_a=ta,
                    team_b=tb,
                    goals_a=ga,
                    goals_b=gb,
                    aet=False,
                    penalties_a=None,
                    penalties_b=None,
                )
            )

    winners_g, runners_up_g, thirds = qualify_from_groups(group_results)
    best_8 = rank_third_place(thirds)
    r32_matchups = build_r32_bracket(winners_g, runners_up_g, best_8)

    all_group = [m for ms in group_results.values() for m in ms]
    ratings = update_ratings(ratings, all_group)
    prob_cache = _build_prob_cache(ratings)

    def _record(matchups: list[tuple[str, str]], phase: str) -> None:
        done = ko_done[phase]
        for ta, tb in matchups:
            if frozenset({ta, tb}) in done:
                continue  # already played; not a "next" match
            qual_counts[ta] += 1
            qual_counts[tb] += 1
            opponent_counts[ta][tb] += 1
            opponent_counts[tb][ta] += 1

    if target_round == "r32":
        _record(r32_matchups, "r32")
        return

    r32_winners, r32_sim = _sim_round(r32_matchups, ko_done["r32"], prob_cache, "r32")
    ratings = update_ratings(ratings, r32_sim)
    prob_cache = _build_prob_cache(ratings)

    r16_matchups = [(r32_winners[a], r32_winners[b]) for a, b in _R16_PAIRS]

    if target_round == "r16":
        _record(r16_matchups, "r16")
        return

    r16_winners, r16_sim = _sim_round(r16_matchups, ko_done["r16"], prob_cache, "r16")
    ratings = update_ratings(ratings, r16_sim)
    prob_cache = _build_prob_cache(ratings)

    qf_matchups = [(r16_winners[a], r16_winners[b]) for a, b in _QF_PAIRS]

    if target_round == "qf":
        _record(qf_matchups, "qf")
        return

    qf_winners, qf_sim = _sim_round(qf_matchups, ko_done["qf"], prob_cache, "qf")
    ratings = update_ratings(ratings, qf_sim)
    prob_cache = _build_prob_cache(ratings)

    sf_matchups = [(qf_winners[a], qf_winners[b]) for a, b in _SF_PAIRS]

    if target_round == "sf":
        _record(sf_matchups, "sf")
        return

    sf_winners, sf_sim = _sim_round(sf_matchups, ko_done["sf"], prob_cache, "sf")
    ratings = update_ratings(ratings, sf_sim)
    prob_cache = _build_prob_cache(ratings)

    # target_round == "final"
    _record([(sf_winners[0], sf_winners[1])], "final")


def run(
    ratings: dict,
    completed: list[MatchResult],
    n: int,
) -> tuple[str, dict, dict]:
    updated = update_ratings(ratings, completed)
    target_round = _detect_target_round(completed)
    ko_done = _completed_ko(completed)

    opponent_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    qual_counts: dict[str, int] = defaultdict(int)

    for _ in range(n):
        _one_sim(
            updated, completed, ko_done, target_round, opponent_counts, qual_counts
        )

    return target_round, opponent_counts, qual_counts


def _print_results(
    target_round: str,
    opponent_counts: dict,
    qual_counts: dict,
    n: int,
    team_filter: str | None,
    top: int | None,
) -> None:
    print(f"Next round: {_ROUND_LABELS[target_round]} ({n:,} simulations)\n")

    for group, teams in GROUPS.items():
        group_teams = sorted(
            [(t, qual_counts.get(t, 0)) for t in teams],
            key=lambda x: -x[1],
        )

        if team_filter:
            group_teams = [
                (t, c) for t, c in group_teams if team_filter.lower() in t.lower()
            ]

        if not any(c > 0 for _, c in group_teams):
            continue

        if not team_filter:
            print(f"Group {group}")

        for team, qc in group_teams:
            if qc == 0:
                continue
            p_qual = qc / n
            print(f"  {team} [qualifies {p_qual:.1%}]")
            opps = sorted(
                ((opp, cnt / qc) for opp, cnt in opponent_counts[team].items()),
                key=lambda x: -x[1],
            )
            if top is not None:
                opps = opps[:top]
            for opp, p in opps:
                if p > 0:
                    print(f"    {p:5.1%}  {opp}")
            print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Next knockout-round opponent probability distribution."
    )
    parser.add_argument("--ratings", default="data/ratings.csv")
    parser.add_argument("--scores", default="data/scores.csv")
    parser.add_argument("-n", type=int, default=1000)
    parser.add_argument(
        "--team", help="Show only this team (case-insensitive substring)"
    )
    parser.add_argument(
        "--top", type=int, default=None, metavar="N",
        help="Limit to the N most probable opponents per team",
    )
    args = parser.parse_args()

    ratings = load_ratings(args.ratings)
    completed = load_scores(args.scores)

    target_round, opponent_counts, qual_counts = run(ratings, completed, args.n)
    _print_results(target_round, opponent_counts, qual_counts, args.n, args.team, args.top)


if __name__ == "__main__":
    main()
