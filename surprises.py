#!/usr/bin/env python3
"""Rank completed World Cup matches by how surprising the result was (initial ratings only)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from src.data import MatchResult, load_ratings, load_scores
from src.ratings import get_probabilities


@dataclass
class SurpriseRecord:
    match: MatchResult
    p_win: float
    p_draw: float
    p_loss: float
    p_actual: float
    outcome_label: str


def build_records(ratings: dict, completed: list[MatchResult]) -> list[SurpriseRecord]:
    records = []
    for m in completed:
        if m.team_a not in ratings or m.team_b not in ratings:
            continue
        p_win, p_draw, p_loss = get_probabilities(ratings[m.team_a], ratings[m.team_b])
        if m.is_draw():
            p_actual, label = p_draw, "Draw"
        elif m.winner() == m.team_a:
            p_actual, label = p_win, f"{m.team_a} win"
        else:
            p_actual, label = p_loss, f"{m.team_b} win"
        records.append(SurpriseRecord(m, p_win, p_draw, p_loss, p_actual, label))
    return records


def score_line(m: MatchResult) -> str:
    suffix = " (AET)" if m.aet and m.penalties_a is None else ""
    if m.penalties_a is not None:
        suffix = f" (pen {m.penalties_a}-{m.penalties_b})"
    return f"{m.team_a} {m.goals_a}-{m.goals_b} {m.team_b}{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List the most surprising match results based on pre-tournament Glicko-2 ratings"
    )
    parser.add_argument(
        "-n", "--top",
        type=int,
        default=10,
        metavar="N",
        help="Number of surprises to show (default: 10)",
    )
    parser.add_argument("--ratings", default="data/ratings.csv", metavar="FILE")
    parser.add_argument("--scores", default="data/scores.csv", metavar="FILE")
    args = parser.parse_args()

    try:
        ratings = load_ratings(args.ratings)
        completed = load_scores(args.scores)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not completed:
        print("No completed matches found.")
        return

    records = build_records(ratings, completed)
    records.sort(key=lambda r: r.p_actual)
    top = records[: args.top]

    n = min(args.top, len(records))
    print(f"\nTop {n} match surprises (initial Glicko-2 ratings)\n")

    for rank, r in enumerate(top, 1):
        m = r.match
        phase_label = f"group {m.group}" if m.group else m.phase
        print(f" #{rank:<3} {score_line(m)}  [{phase_label}]")
        print(
            f"      Expected: {m.team_a} {r.p_win*100:.1f}%"
            f"  |  Draw {r.p_draw*100:.1f}%"
            f"  |  {m.team_b} {r.p_loss*100:.1f}%"
        )
        print(f"      Actual:   {r.outcome_label} — probability {r.p_actual*100:.1f}%")
        print()


if __name__ == "__main__":
    main()
