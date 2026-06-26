from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import date

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from src.data import load_ratings, load_scores
from src.match import score_distribution, simulate_group_match
from src.ratings import get_probabilities, update_ratings

_GOAL_CAP = 8

_ESPN_NAME_MAP: dict[str, str] = {
    "South Korea": "Korea Republic",
    "Türkiye": "Turkey",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Curaçao": "Curacao",
    "Ivory Coast": "Cote d'Ivoire",
    "Côte d'Ivoire": "Cote d'Ivoire",
    "Iran": "IR Iran",
    "Islamic Republic of Iran": "IR Iran",
    "Congo DR": "DR Congo",
    "Democratic Republic of Congo": "DR Congo",
    "Cape Verde": "Cabo Verde",
    "United States": "USA",
}

_LIVE_STATUSES = {"STATUS_IN_PROGRESS", "STATUS_HALFTIME"}


def _normalize(name: str) -> str:
    return _ESPN_NAME_MAP.get(name, name)


def fetch_today_schedule() -> list[dict]:
    today = date.today()
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/"
        f"scoreboard?dates={today.strftime('%Y%m%d')}&limit=20"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"error: could not fetch today's schedule: {exc}", file=sys.stderr)
        return []

    games = []
    for event in data.get("events", []):
        for comp in event.get("competitions", []):
            status = comp.get("status", {})
            status_name = status.get("type", {}).get("name", "")

            competitors = comp.get("competitors", [])
            if len(competitors) != 2:
                continue

            c0, c1 = competitors[0], competitors[1]
            team_a = _normalize(c0["team"]["displayName"])
            team_b = _normalize(c1["team"]["displayName"])

            goals_a = int(c0.get("score", "0") or 0)
            goals_b = int(c1.get("score", "0") or 0)

            alt_note = comp.get("altGameNote", "")
            group = alt_note.split("Group ")[-1].strip() if "Group " in alt_note else ""

            is_live = status_name in _LIVE_STATUSES
            is_done = status_name == "STATUS_FULL_TIME"

            clock = status.get("displayClock", "") if is_live else ""
            period = status.get("period", 0) if is_live else 0

            games.append({
                "team_a": team_a,
                "team_b": team_b,
                "goals_a": goals_a,
                "goals_b": goals_b,
                "group": group,
                "status": "live" if is_live else ("completed" if is_done else "scheduled"),
                "clock": clock,
                "period": period,
                "status_name": status_name,
            })
    return games


def print_today(ratings: dict) -> None:
    games = fetch_today_schedule()
    if not games:
        print("No matches scheduled for today.")
        return

    today = date.today()
    print(f"\nToday's matches — {today}\n")

    _PERIOD_LABEL = {1: "1H", 2: "2H", 3: "ET", 4: "ET"}

    for g in games:
        a, b = g["team_a"], g["team_b"]
        group_label = f"  [Group {g['group']}]" if g["group"] else ""

        if g["status"] == "completed":
            print(f"  {a} {g['goals_a']}-{g['goals_b']} {b}  [FT]{group_label}")
        elif g["status"] == "live":
            clock_str = (
                "HT" if g["status_name"] == "STATUS_HALFTIME"
                else (g["clock"] or _PERIOD_LABEL.get(g["period"], "?"))
            )
            print(f"  {a} {g['goals_a']}-{g['goals_b']} {b}  [{clock_str}]{group_label}")
        else:
            print(f"  {a} vs {b}{group_label}")

        if g["status"] != "completed":
            unknown = [t for t in (a, b) if t not in ratings]
            if unknown:
                print(f"    (unknown team(s): {', '.join(unknown)})")
            else:
                p_win, p_draw, p_loss = get_probabilities(ratings[a], ratings[b])
                print(f"    {a} {p_win*100:.1f}%  |  Draw {p_draw*100:.1f}%  |  {b} {p_loss*100:.1f}%")
                dist = score_distribution(a, b, {(a, b): (p_win, p_draw, p_loss)})
                ks = np.arange(dist.shape[0])
                exp_a = float(np.dot(ks, dist.sum(axis=1)))
                exp_b = float(np.dot(ks, dist.sum(axis=0)))
                print(f"    Expected: {a} {exp_a:.1f}  —  {b} {exp_b:.1f}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Head-to-head matchup simulator: W/D/L odds and scoreline heatmap"
    )
    parser.add_argument("team_a", nargs="?", help="First team name")
    parser.add_argument("team_b", nargs="?", help="Second team name")
    parser.add_argument(
        "--today",
        action="store_true",
        help="Show today's matches with Glicko-2 odds (no simulation)",
    )
    parser.add_argument(
        "-n",
        "--simulations",
        type=int,
        default=1_000,
        metavar="N",
        help="Number of matches to simulate (default: 10,000)",
    )
    parser.add_argument(
        "--ratings",
        default="data/ratings.csv",
        metavar="FILE",
        help="Glicko-2 ratings CSV (default: data/ratings.csv)",
    )
    parser.add_argument(
        "--scores",
        default="data/scores.csv",
        metavar="FILE",
        help="Completed match scores CSV (default: data/scores.csv)",
    )
    parser.add_argument(
        "--save",
        metavar="FILE",
        help="Save chart to file instead of opening a window",
    )
    args = parser.parse_args()

    if not args.today and (not args.team_a or not args.team_b):
        parser.error("team_a and team_b are required unless --today is used")

    try:
        ratings = load_ratings(args.ratings)
        completed = load_scores(args.scores)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    ratings = update_ratings(ratings, completed)

    if args.today:
        print_today(ratings)
        return

    for name in (args.team_a, args.team_b):
        if name not in ratings:
            close = [t for t in ratings if name.lower() in t.lower()]
            hint = f"  Did you mean: {', '.join(close[:5])}" if close else ""
            print(f"error: unknown team '{name}'.{hint}", file=sys.stderr)
            sys.exit(1)

    p_win, p_draw, p_loss = get_probabilities(ratings[args.team_a], ratings[args.team_b])

    cache = {(args.team_a, args.team_b): (p_win, p_draw, p_loss)}

    dist = score_distribution(args.team_a, args.team_b, cache)
    ks = np.arange(dist.shape[0])
    exp_a = float(np.dot(ks, dist.sum(axis=1)))
    exp_b = float(np.dot(ks, dist.sum(axis=0)))

    score_counts: dict[tuple[int, int], int] = defaultdict(int)
    for _ in range(args.simulations):
        ga, gb = simulate_group_match(args.team_a, args.team_b, cache)
        score_counts[(ga, gb)] += 1

    n = args.simulations
    sim_win = sum(v for (ga, gb), v in score_counts.items() if ga > gb) / n * 100
    sim_draw = sum(v for (ga, gb), v in score_counts.items() if ga == gb) / n * 100
    sim_loss = sum(v for (ga, gb), v in score_counts.items() if ga < gb) / n * 100

    a, b = args.team_a, args.team_b
    print(f"\n{a} vs {b}  ({n:,} simulated matches)\n")
    print(f"  Theoretical (Glicko-2):  {a} {p_win*100:.1f}%  |  Draw {p_draw*100:.1f}%  |  {b} {p_loss*100:.1f}%")
    print(f"  Simulated:               {a} {sim_win:.1f}%  |  Draw {sim_draw:.1f}%  |  {b} {sim_loss:.1f}%")
    print(f"  Expected score:          {a} {exp_a:.1f}  —  {b} {exp_b:.1f}")
    print()

    top6 = sorted(score_counts.items(), key=lambda x: x[1], reverse=True)[:6]
    print("  Top scorelines:")
    for (ga, gb), count in top6:
        print(f"    {a} {ga}-{gb} {b}:  {count / n * 100:.1f}%")
    print()

    cap = _GOAL_CAP
    matrix = np.zeros((cap + 1, cap + 1))
    for (ga, gb), count in score_counts.items():
        if ga <= cap and gb <= cap:
            matrix[gb][ga] = count / n * 100

    labels = list(range(cap + 1))

    fig, ax = plt.subplots(figsize=(8, 7))

    sns.heatmap(
        matrix,
        annot=True,
        fmt=".1f",
        xticklabels=labels,
        yticklabels=labels,
        cmap="YlOrRd",
        vmin=0,
        linewidths=0.4,
        linecolor="white",
        ax=ax,
        annot_kws={"size": 8},
        cbar_kws={"label": "Probability (%)"},
    )

    ax.invert_yaxis()
    ax.set_xlabel(f"{a} goals", labelpad=8)
    ax.set_ylabel(f"{b} goals", labelpad=8)
    ax.set_title(
        f"{a} vs {b} — scoreline distribution\n({n:,} simulated matches)",
        pad=12,
    )

    plt.tight_layout()

    if args.save:
        plt.savefig(args.save, dpi=150, bbox_inches="tight")
        print(f"Saved to {args.save}", file=sys.stderr)
    else:
        plt.show()


if __name__ == "__main__":
    main()
