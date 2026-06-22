from __future__ import annotations

import json

from .data import GROUPS, MatchResult
from .simulation import ROUNDS, SimResults

_ROUND_LABELS = {
    "group": "Group",
    "r32": "Round of 32",
    "r16": "Round of 16",
    "qf": "Quarterfinal",
    "sf": "Semifinal",
    "final": "Final",
}


def format_trace(team: str, matches: list[MatchResult]) -> str:
    if not matches:
        return f"No matches found for '{team}'."

    lines = [f"{team} — tournament trace:", ""]
    for m in matches:
        if m.team_a == team:
            opponent = m.team_b
            gf, ga = m.goals_a, m.goals_b
            pf = m.penalties_a
            pa = m.penalties_b
        else:
            opponent = m.team_a
            gf, ga = m.goals_b, m.goals_a
            pf = m.penalties_b
            pa = m.penalties_a

        if pf is not None:
            result = "W" if pf > pa else "L"
        elif gf > ga:
            result = "W"
        elif gf < ga:
            result = "L"
        else:
            result = "D"

        score = f"{gf}–{ga}"
        suffix = " AET" if m.aet else ""
        if pf is not None:
            suffix += f" (pens {pf}–{pa})"

        if m.phase == "group":
            label = f"Group {m.group}"
        else:
            label = _ROUND_LABELS.get(m.phase, m.phase)

        lines.append(f"{label:<15}  {team} {score} {opponent}{suffix}  ({result})")

    return "\n".join(lines)


def _pct(count: int, total: int) -> str:
    if total == 0:
        return " 0.0%"
    return f"{count / total * 100:5.1f}%"


def _goals_per_game(results: SimResults, team: str) -> tuple[float, float]:
    games = 3 * results.n + sum(
        results.round_counts.get(team, {}).get(rnd, 0)
        for rnd in ["r32", "r16", "qf", "sf", "final"]
    )
    if not games:
        return 0.0, 0.0
    gf = sum(results.goals_for.get(team, {}).get(ph, 0) for ph in _GOAL_PHASES)
    ga = sum(results.goals_against.get(team, {}).get(ph, 0) for ph in _GOAL_PHASES)
    return gf / games, ga / games


def format_winner_odds(results: SimResults) -> str:
    header = f"  {'':4}  {'Team':<30} {'Win%':>6}  {'GF/G':>5}  {'GA/G':>5}"
    sep = "  " + "-" * (len(header) - 2)
    lines = ["Tournament winner probabilities:", "", header, sep]
    all_teams = [t for teams in GROUPS.values() for t in teams]
    ranked = sorted(
        all_teams,
        key=lambda t: (
            results.win_counts.get(t, 0),
            results.round_counts.get(t, {}).get("final", 0),
            results.round_counts.get(t, {}).get("sf", 0),
            results.round_counts.get(t, {}).get("qf", 0),
            results.round_counts.get(t, {}).get("r16", 0),
            results.round_counts.get(t, {}).get("r32", 0),
        ),
        reverse=True,
    )
    for i, team in enumerate(ranked, 1):
        pct = _pct(results.win_counts.get(team, 0), results.n)
        gf_pg, ga_pg = _goals_per_game(results, team)
        lines.append(f"  {i:2}.  {team:<30} {pct}  {gf_pg:5.2f}  {ga_pg:5.2f}")
    return "\n".join(lines)
def format_round_probs(results: SimResults) -> str:
    header = f"  {'Team':<30} {'R32':>6} {'R16':>6} {'QF':>6} {'SF':>6} {'Final':>6} {'Win':>6}"
    sep = "  " + "-" * (len(header) - 2)
    lines = ["Round-by-round probabilities:", "", header, sep]

    all_teams = [t for teams in GROUPS.values() for t in teams]
    ranked = sorted(
        all_teams,
        key=lambda t: (
            results.win_counts.get(t, 0),
            results.round_counts.get(t, {}).get("final", 0),
            results.round_counts.get(t, {}).get("sf", 0),
            results.round_counts.get(t, {}).get("qf", 0),
            results.round_counts.get(t, {}).get("r16", 0),
            results.round_counts.get(t, {}).get("r32", 0),
        ),
        reverse=True,
    )

    for team in ranked:
        rc = results.round_counts.get(team, {})
        row = f"  {team:<30}"
        for rnd in ROUNDS:
            if rnd == "win":
                cnt = results.win_counts.get(team, 0)
            else:
                cnt = rc.get(rnd, 0)
            row += f" {_pct(cnt, results.n):>6}"
        lines.append(row)
    return "\n".join(lines)


def format_group_standings(results: SimResults) -> str:
    lines = ["Group standings (most likely positions):", ""]
    for group, teams in GROUPS.items():
        lines.append(f"  Group {group}:")
        # Sort by most common position (weighted average)
        def sort_key(t: str) -> float:
            counts = results.group_pos_counts.get(t, [0, 0, 0, 0])
            total = sum(counts)
            if total == 0:
                return 4.0
            return sum((pos + 1) * c for pos, c in enumerate(counts)) / total

        sorted_teams = sorted(teams, key=sort_key)
        for team in sorted_teams:
            counts = results.group_pos_counts.get(team, [0, 0, 0, 0])
            total = sum(counts) or 1
            ordinals = ["1st", "2nd", "3rd", "4th"]
            dist = "  ".join(f"{ordinals[i]}:{c/total*100:4.1f}%" for i, c in enumerate(counts))
            lines.append(f"    {team:<30} {dist}")
        lines.append("")
    return "\n".join(lines)


_GOAL_PHASES = ["group", "r32", "r16", "qf", "sf", "final"]
_GOAL_PHASE_LABELS = ["Group", "R32", "R16", "QF", "SF", "Final"]


def format_goal_stats(results: SimResults) -> str:
    n = results.n or 1
    lines = ["Average goals per phase per simulation:", ""]

    lines.append(f"  {'Phase':<16} {'Avg goals':>9}")
    lines.append("  " + "-" * 26)
    for phase, label in zip(_GOAL_PHASES, _GOAL_PHASE_LABELS):
        avg = results.phase_goals.get(phase, 0) / n
        lines.append(f"  {label:<16} {avg:9.1f}")

    lines.append("")
    lines.append("Average goals scored per team per simulation:")
    lines.append("")

    header = f"  {'Team':<30}" + "".join(f" {lbl:>6}" for lbl in _GOAL_PHASE_LABELS) + f" {'Total':>7}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    all_teams = [t for teams in GROUPS.values() for t in teams]
    totals = {
        t: sum(results.goals_for.get(t, {}).get(ph, 0) for ph in _GOAL_PHASES) / n
        for t in all_teams
    }
    for team in sorted(all_teams, key=lambda t: totals[t], reverse=True):
        row = f"  {team:<30}"
        for phase in _GOAL_PHASES:
            avg = results.goals_for.get(team, {}).get(phase, 0) / n
            row += f" {avg:6.2f}"
        row += f" {totals[team]:7.2f}"
        lines.append(row)

    return "\n".join(lines)


def format_text(results: SimResults) -> str:
    divider = "\n" + "=" * 60 + "\n"
    return divider.join([
        format_winner_odds(results),
        format_round_probs(results),
        format_group_standings(results),
        format_goal_stats(results),
    ])


def format_json(results: SimResults) -> str:
    all_teams = [t for teams in GROUPS.values() for t in teams]

    def safe_pct(cnt: int) -> float:
        return round(cnt / results.n * 100, 2) if results.n else 0.0

    data = {
        "simulations": results.n,
        "winner_odds": {
            t: safe_pct(results.win_counts.get(t, 0)) for t in all_teams
        },
        "round_reach": {
            t: {
                rnd: safe_pct(
                    results.win_counts.get(t, 0)
                    if rnd == "win"
                    else results.round_counts.get(t, {}).get(rnd, 0)
                )
                for rnd in ROUNDS
            }
            for t in all_teams
        },
        "group_positions": {
            t: {
                str(pos + 1): round(c / (sum(results.group_pos_counts.get(t, [1])) or 1) * 100, 2)
                for pos, c in enumerate(results.group_pos_counts.get(t, [0, 0, 0, 0]))
            }
            for t in all_teams
        },
        "goal_stats": {
            "phase_totals": {
                phase: round(results.phase_goals.get(phase, 0) / (results.n or 1), 2)
                for phase in _GOAL_PHASES
            },
            "by_team": {
                t: {
                    **{
                        phase: round(results.goals_for.get(t, {}).get(phase, 0) / (results.n or 1), 2)
                        for phase in _GOAL_PHASES
                    },
                    "total": round(
                        sum(results.goals_for.get(t, {}).get(ph, 0) for ph in _GOAL_PHASES) / (results.n or 1), 2
                    ),
                }
                for t in all_teams
            },
        },
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
