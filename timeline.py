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

from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D

from src.data import load_ratings, load_scores, GROUPS, TEAM_TO_GROUP
from src.ratings import update_ratings
from src.simulation import run_simulations, SimResults

ROUNDS = ["win", "final", "sf", "qf", "r16", "r32"]
ALL_TEAMS = [t for teams in GROUPS.values() for t in teams]


def _compute_date_probs(results: SimResults, n: int) -> dict[str, dict[str, float]]:
    """Convert SimResults to percentage dicts keyed by round."""
    probs: dict[str, dict[str, float]] = {}
    for r in ROUNDS:
        if r == "win":
            # wins are stored in win_counts, not round_counts
            probs[r] = {t: results.win_counts.get(t, 0) / n * 100 for t in ALL_TEAMS}
        else:
            probs[r] = {
                t: results.round_counts[t].get(r, 0) / n * 100
                for t in results.round_counts
            }
    return probs


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


def _snapshot_chart(
    ratings_initial: dict,
    ratings_current: dict,
    probs_initial: dict[str, float],
    probs_current: dict[str, float],
    n: int,
    save: str | None,
) -> None:
    """Two-panel slope chart: Y = value scale, X = pre-tournament vs current.

    Flat line   → as expected (gray).
    Rising line → better than expected (green; darker = more improvement).
    Falling line → worse than expected (red; darker = larger drop).
    """
    # Lines: lighter gradient with alpha to show magnitude visually
    line_cmap = LinearSegmentedColormap.from_list(
        "rg", ["#cc2222", "#aaaaaa", "#22aa22"]
    )
    # Labels: darker variant so text is always legible on white background
    label_cmap = LinearSegmentedColormap.from_list(
        "rg_dark", ["#7a0000", "#303030", "#004a00"]
    )

    panels = [
        (
            {t: ratings_initial[t].rating for t in ALL_TEAMS},
            {t: ratings_current[t].rating for t in ALL_TEAMS},
            "Glicko-2 rating",
        ),
        (
            probs_initial,
            probs_current,
            "Win probability (%)",
        ),
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 16))
    fig.subplots_adjust(left=0.18, right=0.82, top=0.94, bottom=0.06, wspace=0.55)

    for ax, (initial_vals, current_vals, ylabel), label_side in zip(
        (ax1, ax2), panels, ("left", "right")
    ):
        deltas = {t: current_vals.get(t, 0) - initial_vals.get(t, 0) for t in ALL_TEAMS}
        max_abs = max((abs(d) for d in deltas.values()), default=1.0) or 1.0
        norm = Normalize(vmin=-max_abs, vmax=max_abs)

        # Draw flattest lines first so big movers appear on top
        for team in sorted(ALL_TEAMS, key=lambda t: abs(deltas[t])):
            y0 = initial_vals.get(team, 0)
            y1 = current_vals.get(team, 0)
            delta = deltas[team]
            magnitude = abs(delta) / max_abs
            cmap_pos = norm(delta) * 0.85 + 0.075  # keep off pure cmap ends
            line_color = line_cmap(cmap_pos)
            label_color = label_cmap(cmap_pos)
            lw = 0.7 + 1.3 * magnitude
            alpha = 0.40 + 0.50 * magnitude
            ax.plot([0, 1], [y0, y1], color=line_color, lw=lw, alpha=alpha)

            label_y = y0 if label_side == "left" else y1
            label_x = -0.04 if label_side == "left" else 1.04
            ha = "right" if label_side == "left" else "left"
            ax.text(
                label_x,
                label_y,
                team,
                ha=ha,
                va="center",
                fontsize=5.5,
                color=label_color,
                alpha=0.9,
                clip_on=False,
            )

        ax.set_xlim(0, 1)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Pre-tournament", "Current"], fontsize=8)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.tick_params(axis="y", labelsize=7)

        ax.grid(False)
        if label_side == "left":
            # Move axis label to the right so it doesn't overlap the country names on the left
            ax.yaxis.set_label_position("right")

    fig.legend(
        handles=[
            Line2D([0], [0], color="#22aa22", lw=2, label="Better than expected ↑"),
            Line2D([0], [0], color="#aaaaaa", lw=0.8, label="As expected →"),
            Line2D([0], [0], color="#cc2222", lw=2, label="Worse than expected ↓"),
        ],
        fontsize=7,
        loc="lower center",
        ncol=3,
        bbox_to_anchor=(0.5, 0.01),
    )

    fig.suptitle(
        f"FIFA World Cup 2026 — ratings & win odds snapshot  ({n:,} simulations)",
        fontsize=9,
        y=0.97,
    )

    if save:
        plt.savefig(save, dpi=150, bbox_inches="tight")
        print(f"Saved to {save}", file=sys.stderr)
    else:
        plt.show()


def _run_and_cache(
    all_completed: list,
    dates: list[str],
    ratings: dict,
    n: int,
    cache: dict,
    cache_path: Path,
    force: bool,
) -> None:
    meta = cache.setdefault("_meta", {})
    for date in dates:
        filtered = [m for m in all_completed if m.date and m.date <= date]
        n_matches = len(filtered)
        cached_wins = cache.get(date, {}).get("win", {})
        win_ok = any(v > 0 for v in cached_wins.values())
        if not force and date in cache and meta.get(date) == n_matches and win_ok:
            print(f"  {date}: cached")
            continue
        label = "stale" if (not force and date in cache) else "simulating"
        print(f"  {date}: {label} ({n_matches} results) ...", end=" ", flush=True)
        results = run_simulations(ratings, filtered, n)
        cache[date] = _compute_date_probs(results, results.n)
        meta[date] = n_matches
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
    parser.add_argument(
        "--save", metavar="FILE", help="Save chart to PNG instead of displaying"
    )
    parser.add_argument(
        "--teams", metavar="TEAMS", help="Comma-separated list of teams to highlight"
    )
    parser.add_argument(
        "--groups", metavar="GROUPS", help="Comma-separated list of groups to highlight (e.g. A,B)"
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Ignore and overwrite existing cache"
    )
    parser.add_argument(
        "--win-prob",
        action="store_true",
        help="Plot tournament win probability (%) instead of rank",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Two-panel before/after chart: ratings and win probability (no timeline needed)",
    )
    args = parser.parse_args()

    n = args.simulations
    ratings = load_ratings(args.ratings)
    all_completed = load_scores(args.scores)

    if args.snapshot:
        cache_path = (
            Path(args.cache) if args.cache else Path(f"cache/timeline_{n}.json")
        )
        # Always load the existing cache so timeline data is preserved when --no-cache
        # regenerates the snapshot entries (--no-cache means "recompute", not "destroy").
        cache: dict = {}
        if cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Baseline (pre-tournament) — bypass cache when --no-cache or all "win" values
        # are zero (indicates an old stale entry written before the win_counts fix).
        baseline_wins = (
            {} if args.no_cache else cache.get("_baseline", {}).get("win", {})
        )
        if any(v > 0 for v in baseline_wins.values()):
            probs_init = baseline_wins
            print("  baseline: cached")
        else:
            print(f"Running {n:,} simulations (pre-tournament)...", file=sys.stderr)
            res_init = run_simulations(ratings, [], n)
            probs_init = {t: res_init.win_counts.get(t, 0) / n * 100 for t in ALL_TEAMS}
            cache["_baseline"] = _compute_date_probs(res_init, n)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

        # Current — use the latest dated timeline entry when fresh and match count matches.
        # Bypass when --no-cache or all "win" values are zero (stale entry).
        completed_dates = sorted({m.date for m in all_completed if m.date})
        latest = completed_dates[-1] if completed_dates else None
        meta = cache.get("_meta", {})
        n_latest = (
            sum(1 for m in all_completed if m.date and m.date <= latest)
            if latest
            else 0
        )
        cached_curr_wins = (
            {}
            if (args.no_cache or not latest)
            else cache.get(latest, {}).get("win", {})
        )
        if (
            any(v > 0 for v in cached_curr_wins.values())
            and meta.get(latest) == n_latest
        ):
            probs_curr = cached_curr_wins
            print(f"  current ({latest}): cached")
        else:
            print(f"Running {n:,} simulations (current)...", file=sys.stderr)
            res_curr = run_simulations(ratings, all_completed, n)
            probs_curr = {t: res_curr.win_counts.get(t, 0) / n * 100 for t in ALL_TEAMS}
            if latest:
                cache[latest] = _compute_date_probs(res_curr, n)
                cache.setdefault("_meta", {})[latest] = n_latest
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

        ratings_current = update_ratings(ratings, all_completed)
        _snapshot_chart(ratings, ratings_current, probs_init, probs_curr, n, args.save)
        return

    cache_path = Path(args.cache) if args.cache else Path(f"cache/timeline_{n}.json")

    dates = sorted({m.date for m in all_completed if m.date})
    if not dates:
        print(
            "No dated results found in scores.csv.\n"
            "Run: uv run update_scores.py  to back-fill dates.",
            file=sys.stderr,
        )
        sys.exit(1)

    cache: dict = {}
    if not args.no_cache and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    print(f"Dates with results: {len(dates)}  |  cache: {cache_path}")
    _run_and_cache(all_completed, dates, ratings, n, cache, cache_path, args.no_cache)

    # Build per-team series: dates and y-values (active dates only)
    team_xs: dict[str, list[datetime]] = {t: [] for t in ALL_TEAMS}
    team_ys: dict[str, list[float]] = {t: [] for t in ALL_TEAMS}

    for date in dates:
        probs = cache[date]
        if args.win_prob:
            for team in ALL_TEAMS:
                if _is_active(team, probs):
                    team_xs[team].append(datetime.fromisoformat(date))
                    team_ys[team].append(probs["win"].get(team, 0))
        else:
            ranks = _rank_teams(probs)
            for team in ALL_TEAMS:
                if _is_active(team, probs):
                    team_xs[team].append(datetime.fromisoformat(date))
                    team_ys[team].append(ranks[team])

    highlight_teams  = set(args.teams.split(","))  if args.teams  else set()
    highlight_groups = set(args.groups.split(",")) if args.groups else set()
    has_filter = bool(highlight_teams or highlight_groups)

    # Assign a color per group using tab20
    cmap = plt.colormaps["tab20"]
    group_color = {g: cmap(i / 12) for i, g in enumerate(GROUPS)}

    fig, ax = plt.subplots(figsize=(15, 9))

    for team in ALL_TEAMS:
        if not team_xs[team]:
            continue
        group = TEAM_TO_GROUP[team]
        color = group_color[group]
        is_highlighted = not has_filter or team in highlight_teams or group in highlight_groups
        alpha = 1.0 if is_highlighted else 0.15
        lw = 1.8 if team in highlight_teams else 1.0
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

    if args.win_prob:
        ax.set_title(
            f"FIFA World Cup 2026 — tournament win probability per match day\n"
            f"({n:,} simulations per day)",
            pad=10,
        )
        ax.set_ylabel("Win probability (%)")
    else:
        ax.invert_yaxis()
        ax.set_title(
            f"FIFA World Cup 2026 — simulated ranking per match day\n"
            f"({n:,} simulations per day)",
            pad=10,
        )
        ax.set_ylabel("Rank  (1 = most likely winner)")

    ax.set_xlabel("Date")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    fig.autofmt_xdate()
    ax.grid(axis="x", alpha=0.25)

    plt.tight_layout()

    if args.save:
        plt.savefig(args.save, dpi=150, bbox_inches="tight")
        print(f"Saved to {args.save}", file=sys.stderr)
    else:
        plt.show()


if __name__ == "__main__":
    main()
