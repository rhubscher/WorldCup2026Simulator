from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .data import load_ratings, load_scores
from .output import format_json, format_text, format_trace
from .simulation import (
    deserialize_results,
    run_simulations,
    serialize_results,
    trace_team,
)

_DEFAULT_CACHE = Path("cache/main.json")


def _load_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
        default=1_000,
        metavar="N",
        help="Number of Monte Carlo simulation runs (default: 1000)",
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
    parser.add_argument(
        "--cache",
        metavar="FILE",
        default=str(_DEFAULT_CACHE),
        help=f"Cache file path (default: {_DEFAULT_CACHE})",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore and overwrite any existing cached simulation result",
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

    cache_path = Path(args.cache)
    cache = {} if args.no_cache else _load_cache(cache_path)
    meta = cache.get("_meta", {})
    n_completed = len(completed)

    if (
        not args.no_cache
        and "results" in cache
        and meta.get("n_matches") == n_completed
        and meta.get("n") == args.simulations
    ):
        print("Using cached simulation results.", file=sys.stderr)
        results = deserialize_results(cache["results"])
    else:
        print(f"Running {args.simulations:,} simulations…", file=sys.stderr)
        results = run_simulations(ratings, completed, args.simulations)
        _save_cache(cache_path, {
            "_meta": {"n_matches": n_completed, "n": args.simulations},
            "results": serialize_results(results),
        })

    if args.output == "json":
        print(format_json(results))
    else:
        print(format_text(results))
