#!/usr/bin/env python3
"""Fetch completed World Cup 2026 match results from ESPN and update data/scores.csv."""

import argparse
import csv
import json
import random
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# ESPN team display names that differ from the canonical names in scores.csv / data.py
ESPN_NAME_MAP: dict[str, str] = {
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

TOURNAMENT_START = date(2026, 6, 11)

LIVE_STATUSES = {"STATUS_IN_PROGRESS", "STATUS_HALFTIME"}

FIELDNAMES = [
    "phase",
    "group",
    "team_a",
    "team_b",
    "goals_a",
    "goals_b",
    "aet",
    "penalties_a",
    "penalties_b",
    "date",
]


def normalize(name: str) -> str:
    return ESPN_NAME_MAP.get(name, name)


def linescore_value(ls: list[dict], period_idx: int) -> int:
    if period_idx >= len(ls):
        return 0
    entry = ls[period_idx]
    raw = entry.get("value", entry.get("displayValue", "0"))
    try:
        return int(float(str(raw)))
    except (TypeError, ValueError):
        return 0


def fetch_day(match_date: date) -> list[dict]:
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/"
        f"scoreboard?dates={match_date.strftime('%Y%m%d')}&limit=20"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"  Warning: could not fetch {match_date}: {exc}", file=sys.stderr)
        return []

    results = []
    for event in data.get("events", []):
        for comp in event.get("competitions", []):
            status = comp.get("status", {})
            status_name = status.get("type", {}).get("name", "")
            is_live = status_name in LIVE_STATUSES
            if status_name != "STATUS_FULL_TIME" and not is_live:
                continue

            # Extract group letter from "FIFA World Cup, Group D"
            alt_note = comp.get("altGameNote", "")
            group = alt_note.split("Group ")[-1].strip() if "Group " in alt_note else ""

            competitors = comp.get("competitors", [])
            if len(competitors) != 2:
                continue

            c0, c1 = competitors[0], competitors[1]
            team0 = normalize(c0["team"]["displayName"])
            team1 = normalize(c1["team"]["displayName"])

            goals0 = int(c0.get("score", "0") or 0)
            goals1 = int(c1.get("score", "0") or 0)

            if is_live:
                results.append(
                    {
                        "team0": team0,
                        "team1": team1,
                        "goals0": goals0,
                        "goals1": goals1,
                        "aet": False,
                        "pen0": None,
                        "pen1": None,
                        "live": True,
                        "clock": status.get("displayClock", ""),
                        "period": status.get("period", 0),
                        "status_name": status_name,
                    }
                )
                continue

            ls0: list[dict] = c0.get("linescores", [])
            ls1: list[dict] = c1.get("linescores", [])
            num_periods = max(len(ls0), len(ls1))

            # Periods: 0=1H, 1=2H, 2=ET1H, 3=ET2H, 4=Penalties
            aet = num_periods >= 3
            has_penalties = num_periods >= 5

            # ESPN score field = regulation + AET goals (penalties are NOT included)
            pen0 = pen1 = None
            if has_penalties:
                pen0 = linescore_value(ls0, 4)
                pen1 = linescore_value(ls1, 4)
                # Verify: ESPN score should equal sum of periods 0-3
                reg_aet0 = sum(linescore_value(ls0, i) for i in range(4))
                if reg_aet0 != goals0:
                    # If ESPN already subtracted penalties from score, trust linescores
                    goals0 = reg_aet0
                    goals1 = sum(linescore_value(ls1, i) for i in range(4))

            results.append(
                {
                    "team0": team0,
                    "team1": team1,
                    "goals0": goals0,
                    "goals1": goals1,
                    "aet": aet,
                    "pen0": pen0,
                    "pen1": pen1,
                    "live": False,
                    "clock": "",
                    "period": 0,
                    "status_name": status_name,
                }
            )
    return results


def main(scores_path: Path, dry_run: bool = False, days: int = 1) -> None:
    with scores_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    pair_to_idx: dict[frozenset, int] = {
        frozenset({r["team_a"], r["team_b"]}): i for i, r in enumerate(rows)
    }

    today = date.today()

    undated = any(
        r.get("goals_a", "").strip() and not r.get("date", "").strip()
        for r in rows
    )
    if undated:
        current = TOURNAMENT_START
        print("Backfilling dates for existing scores from tournament start...")
    else:
        current = max(TOURNAMENT_START, today - timedelta(days=days - 1))

    total_updated = 0

    while current <= today:
        print(f"Fetching {current}...", end=" ", flush=True)
        day_results = fetch_day(current)
        completed_results = [m for m in day_results if not m["live"]]
        live_results = [m for m in day_results if m["live"]]
        print(f"{len(completed_results)} completed, {len(live_results)} in progress")

        for m in completed_results:
            pair = frozenset({m["team0"], m["team1"]})
            if pair not in pair_to_idx:
                print(f"  SKIP (unrecognized): {m['team0']} vs {m['team1']}")
                continue

            idx = pair_to_idx[pair]
            row = rows[idx]

            has_score = bool(row.get("goals_a", "").strip())
            has_date = bool(row.get("date", "").strip())

            if has_score and has_date:
                continue  # fully recorded

            # Orient score to match team_a / team_b order in the CSV
            if row["team_a"] == m["team0"]:
                goals_a, goals_b = m["goals0"], m["goals1"]
                pen_a, pen_b = m["pen0"], m["pen1"]
            else:
                goals_a, goals_b = m["goals1"], m["goals0"]
                pen_a, pen_b = m["pen1"], m["pen0"]

            if not has_score:
                suffix = " (AET)" if m["aet"] else ""
                if pen_a is not None:
                    suffix += f" pen {pen_a}-{pen_b}"
                print(f"  {row['team_a']} {goals_a}-{goals_b} {row['team_b']}{suffix}")
            else:
                print(f"  {row['team_a']} vs {row['team_b']} — date backfilled")

            if not dry_run:
                if not has_score:
                    row["goals_a"] = str(goals_a)
                    row["goals_b"] = str(goals_b)
                    row["aet"] = "true" if m["aet"] else ""
                    row["penalties_a"] = str(pen_a) if pen_a is not None else ""
                    row["penalties_b"] = str(pen_b) if pen_b is not None else ""
                row["date"] = current.isoformat()

            total_updated += 1

        if live_results and current == today:
            PERIOD_LABEL = {1: "1H", 2: "2H", 3: "ET", 4: "ET"}
            for m in live_results:
                label = (
                    "HT"
                    if m["status_name"] == "STATUS_HALFTIME"
                    else (m["clock"] or PERIOD_LABEL.get(m["period"], "?"))
                )
                print(
                    f"  {m['team0']} {m['goals0']}-{m['goals1']} {m['team1']}  [{label}] IN PROGRESS"
                )

        time.sleep(random.uniform(3, 7))
        current += timedelta(days=1)

    if total_updated == 0:
        print("No new results to update.")
        return

    if dry_run:
        print(f"\nDry run: {total_updated} result(s) would be updated.")
        return

    with scores_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, restval="")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nUpdated {total_updated} result(s) in {scores_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Update scores.csv from ESPN API")
    p.add_argument("--scores", default="data/scores.csv", help="Path to scores CSV")
    p.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing"
    )
    p.add_argument(
        "--days",
        type=int,
        default=1,
        metavar="N",
        help="Number of days to scan back from today (default: 1 = today only)",
    )
    args = p.parse_args()
    main(Path(args.scores), dry_run=args.dry_run, days=args.days)
