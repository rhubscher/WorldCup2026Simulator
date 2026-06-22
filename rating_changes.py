#!/usr/bin/env python3
"""List teams performing much better/worse than expected, based on rating drift since the tournament started."""

from __future__ import annotations

import argparse
import sys

from src.data import load_ratings, load_scores
from src.ratings import update_ratings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List teams whose rating has moved the most from their pre-tournament baseline"
    )
    parser.add_argument(
        "-n", "--top",
        type=int,
        default=3,
        metavar="N",
        help="Number of teams to show in each direction (default: 3)",
    )
    parser.add_argument("--ratings", default="data/ratings.csv", metavar="FILE")
    parser.add_argument("--scores", default="data/scores.csv", metavar="FILE")
    args = parser.parse_args()

    try:
        initial = load_ratings(args.ratings)
        completed = load_scores(args.scores)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not completed:
        print("No completed matches found.")
        return

    current = update_ratings(initial, completed)

    deltas = sorted(
        ((team, current[team].rating - initial[team].rating) for team in initial),
        key=lambda x: x[1],
        reverse=True,
    )

    n = min(args.top, len(deltas))
    better = deltas[:n]
    worse = sorted(deltas, key=lambda x: x[1])[:n]

    print(f"\nTop {n} performing better than expected (rating up the most)\n")
    for team, delta in better:
        print(f"  {team:<25} {initial[team].rating:.0f} -> {current[team].rating:.0f}  ({delta:+.0f})")

    print(f"\nTop {n} performing worse than expected (rating down the most)\n")
    for team, delta in worse:
        print(f"  {team:<25} {initial[team].rating:.0f} -> {current[team].rating:.0f}  ({delta:+.0f})")
    print()


if __name__ == "__main__":
    main()
