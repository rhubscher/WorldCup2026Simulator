#!/usr/bin/env python3
"""Line chart showing each team's simulated ranking over match days."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from src.data import load_ratings, load_scores, GROUPS, TEAM_TO_GROUP
from src.simulation import run_simulations

ROUNDS = ["win", "final", "sf", "qf", "r16", "r32"]
ALL_TEAMS = [t for teams in GROUPS.values() for t in teams]


def _compute_date_probs(results: object, n: int) -> dict[str, dict[str, float]]:
    """Convert SimResults round_counts to percentage dicts keyed by round."""
    return {
        r: {t: results.round_counts[t].get(r, 0) / n * 100 for t in results.round_counts}
        for r in ROUNDS
    }


def _is_active(team: str, probs: dict[str, dict[str, float]]) -> bool:
    """Return True if team is still in the tournament (not yet eliminated)."""
    p = [probs[r].get(team, 0) for r in ROUNDS]
    # p[0]=win, p[1]=final, p[2]=sf, p[3]=qf, p[4]=r16, p[5]=r32
    # Find highest round they've definitely reached (≥99.5%) and check if they
    # can still advance past it.
    for i in range(len(ROUNDS) - 1):  # win..r16
        if p[i] > 99.5:
            return True  # definitely won the tournament or past that point
        if p[i + 1] > 99.5:
            # Definitely reached round i+1; do they still have a future?
            return p[i] > 0.01
    # No certain round reached yet → still in group stage
    return p[-1] > 0.01  # r32 probability


def _rank_teams(probs: dict[str, dict[str, float]]) -> dict[str, int]:
    """Rank all 48 teams by composite probability; rank 1 = best."""
    sorted_teams = sorted(
        ALL_TEAMS,
        key=lambda t: tuple(-(probs[r].get(t, 0)) for r in ROUNDS),
    )
    return {t: i + 1 for i, t in enumerate(sorted_teams)}


def _run_and_cache(
    all_completed: list,
    dates: list[str],
    ratings: dict,
    n: int,
    cache: dict,
    cache_path: Path,
    force: bool,
) -> None:
    for date in dates:
        if not force and date in cache:
            print(f"  {date}: cached")
            continue
        filtered = [m for m in all_completed if m.date and m.date <= date]
        print(f"  {date}: simulating ({len(filtered)} results) ...", end=" ", flush=True)
        results = run_simulations(ratings, filtered, n)
        cache[date] = _compute_date_probs(results, results.n)
        print("done")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Line chart of simulated ranking per team over each match day"
    )
    parser.add_argument("--scores", default="data/scores.csv")
    parser.add_argument("--ratings", default="data/ratings.csv")
    parser.add_argument("-n", "--simulations", type=int, default=2000, metavar="N")
    parser.add_argument("--cache", metavar="FILE", help="Cache file path")
    parser.add_argument("--save", metavar="FILE", help="Save chart to PNG instead of displaying")
    parser.add_argument("--teams", metavar="TEAMS", help="Comma-separated list of teams to highlight")
    parser.add_argument("--no-cache", action="store_true", help="Ignore and overwrite existing cache")
    args = parser.parse_args()

    n = args.simulations
    cache_path = Path(args.cache) if args.cache else Path(f"cache/timeline_{n}.json")

    ratings = load_ratings(args.ratings)
    all_completed = load_scores(args.scores)

    dates = sorted({m.date for m in all_completed if m.date})
    if not dates:
        print(
            "No dated results found in scores.csv.\n"
            "Run: uv run update_scores.py --days 30  to back-fill dates.",
            file=sys.stderr,
        )
        sys.exit(1)

    cache: dict = {}
    if not args.no_cache and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    print(f"Dates with results: {len(dates)}  |  cache: {cache_path}")
    _run_and_cache(all_completed, dates, ratings, n, cache, cache_path, args.no_cache)

    # Build per-team series: dates and ranks (active dates only)
    team_xs: dict[str, list[datetime]] = {t: [] for t in ALL_TEAMS}
    team_ys: dict[str, list[int]] = {t: [] for t in ALL_TEAMS}

    for date in dates:
        probs = cache[date]
        ranks = _rank_teams(probs)
        for team in ALL_TEAMS:
            if _is_active(team, probs):
                team_xs[team].append(datetime.fromisoformat(date))
                team_ys[team].append(ranks[team])

    highlight = set(args.teams.split(",")) if args.teams else set()

    # Assign a color per group using tab20
    cmap = plt.colormaps["tab20"]
    group_color = {g: cmap(i / 12) for i, g in enumerate(GROUPS)}

    fig, ax = plt.subplots(figsize=(15, 9))

    for team in ALL_TEAMS:
        if not team_xs[team]:
            continue
        group = TEAM_TO_GROUP[team]
        color = group_color[group]
        is_highlighted = not highlight or team in highlight
        alpha = 1.0 if is_highlighted else 0.15
        lw = 1.8 if team in highlight else 1.0
        ax.plot(team_xs[team], team_ys[team], color=color, alpha=alpha, linewidth=lw)
        ax.annotate(
            team,
            xy=(team_xs[team][-1], team_ys[team][-1]),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            fontsize=6,
            color=color,
            alpha=1.0 if is_highlighted else 0.55,
        )

    ax.invert_yaxis()
    ax.set_title(
        f"FIFA World Cup 2026 — simulated ranking per match day\n"
        f"({n:,} simulations per day)",
        pad=10,
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Rank  (1 = most likely winner)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    fig.autofmt_xdate()
    ax.grid(True, alpha=0.25)

    legend_handles = [
        plt.Line2D([0], [0], color=group_color[g], linewidth=2, label=f"Group {g}")
        for g in GROUPS
    ]
    ax.legend(handles=legend_handles, fontsize=7, ncol=2, loc="upper left")

    plt.tight_layout()

    if args.save:
        plt.savefig(args.save, dpi=150, bbox_inches="tight")
        print(f"Saved to {args.save}", file=sys.stderr)
    else:
        plt.show()


if __name__ == "__main__":
    main()
