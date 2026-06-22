from __future__ import annotations

import argparse
import sys

from .data import load_ratings, load_scores
from .output import format_json, format_text, format_trace
from .simulation import run_simulations, trace_team


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FIFA World Cup 2026 Monte Carlo simulator"
    )
    parser.add_argument(
        "--ratings",
        default="data/ratings.csv",
        metavar="FILE",
        help="Path to Glicko-2 ratings CSV (default: data/ratings.csv)",
    )
    parser.add_argument(
        "--scores",
        default="data/scores.csv",
        metavar="FILE",
        help="Path to completed match scores CSV (default: data/scores.csv)",
    )
    parser.add_argument(
        "-n",
        "--simulations",
        type=int,
        default=10_000,
        metavar="N",
        help="Number of Monte Carlo simulation runs (default: 10000)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--trace",
        metavar="TEAM",
        help="Print one-run match diary for TEAM (ignores -n and --output)",
    )
    args = parser.parse_args()

    try:
        ratings = load_ratings(args.ratings)
        completed = load_scores(args.scores)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error loading input: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.trace:
        matches = trace_team(ratings, completed, args.trace)
        print(format_trace(args.trace, matches))
        return

    print(f"Running {args.simulations:,} simulations…", file=sys.stderr)
    results = run_simulations(ratings, completed, args.simulations)

    if args.output == "json":
        print(format_json(results))
    else:
        print(format_text(results))
