from __future__ import annotations

import random
from dataclasses import dataclass, field
from itertools import combinations

from .data import GROUPS, MatchResult


@dataclass
class TeamStats:
    team: str
    points: int = 0
    gd: int = 0
    gf: int = 0


def _head_to_head_points(team: str, others: list[str], results: list[MatchResult]) -> int:
    pts = 0
    for r in results:
        if {r.team_a, r.team_b} == {team} | set(others) - {team}:
            continue
        if r.team_a not in others and r.team_b not in others:
            continue
        if r.team_a == team or r.team_b == team:
            if r.team_a not in others and r.team_b not in others:
                continue
            if r.team_a == team and r.team_b in others:
                if r.goals_a > r.goals_b:
                    pts += 3
                elif r.goals_a == r.goals_b:
                    pts += 1
            elif r.team_b == team and r.team_a in others:
                if r.goals_b > r.goals_a:
                    pts += 3
                elif r.goals_a == r.goals_b:
                    pts += 1
    return pts


def _h2h_points_among(teams: list[str], results: list[MatchResult]) -> dict[str, int]:
    pts: dict[str, int] = {t: 0 for t in teams}
    team_set = set(teams)
    for r in results:
        if r.team_a in team_set and r.team_b in team_set:
            if r.goals_a > r.goals_b:
                pts[r.team_a] += 3
            elif r.goals_a == r.goals_b:
                pts[r.team_a] += 1
                pts[r.team_b] += 1
            else:
                pts[r.team_b] += 3
    return pts


def _h2h_gd_among(teams: list[str], results: list[MatchResult]) -> dict[str, int]:
    gd: dict[str, int] = {t: 0 for t in teams}
    team_set = set(teams)
    for r in results:
        if r.team_a in team_set and r.team_b in team_set:
            diff = r.goals_a - r.goals_b
            gd[r.team_a] += diff
            gd[r.team_b] -= diff
    return gd


def _h2h_gf_among(teams: list[str], results: list[MatchResult]) -> dict[str, int]:
    gf: dict[str, int] = {t: 0 for t in teams}
    team_set = set(teams)
    for r in results:
        if r.team_a in team_set and r.team_b in team_set:
            gf[r.team_a] += r.goals_a
            gf[r.team_b] += r.goals_b
    return gf


def _sort_key_with_h2h(
    tied_teams: list[str], all_stats: dict[str, TeamStats], results: list[MatchResult]
) -> list[str]:
    """Sort tied teams using head-to-head then random. Returns sorted list (best first)."""
    if len(tied_teams) == 1:
        return tied_teams

    h2h_pts = _h2h_points_among(tied_teams, results)
    h2h_gd = _h2h_gd_among(tied_teams, results)
    h2h_gf = _h2h_gf_among(tied_teams, results)

    def key(t: str):
        return (h2h_pts[t], h2h_gd[t], h2h_gf[t], random.random())

    return sorted(tied_teams, key=key, reverse=True)


def rank_group(group_results: list[MatchResult], teams: list[str]) -> list[TeamStats]:
    """Rank 4 teams in a group; returns list ordered 1st–4th."""
    stats: dict[str, TeamStats] = {t: TeamStats(team=t) for t in teams}

    for r in group_results:
        if r.team_a not in stats or r.team_b not in stats:
            continue
        sa, sb = stats[r.team_a], stats[r.team_b]
        sa.gf += r.goals_a
        sb.gf += r.goals_b
        diff = r.goals_a - r.goals_b
        sa.gd += diff
        sb.gd -= diff
        if r.goals_a > r.goals_b:
            sa.points += 3
        elif r.goals_a == r.goals_b:
            sa.points += 1
            sb.points += 1
        else:
            sb.points += 3

    # Sort by points, then GD, then GF; break ties with head-to-head then random
    def overall_key(t: str) -> tuple:
        s = stats[t]
        return (s.points, s.gd, s.gf)

    sorted_teams = sorted(teams, key=overall_key, reverse=True)

    # Resolve ties between teams with equal overall stats
    result_order: list[str] = []
    i = 0
    while i < len(sorted_teams):
        j = i + 1
        while j < len(sorted_teams) and overall_key(sorted_teams[j]) == overall_key(sorted_teams[i]):
            j += 1
        tied = sorted_teams[i:j]
        if len(tied) > 1:
            tied = _sort_key_with_h2h(tied, stats, group_results)
        result_order.extend(tied)
        i = j

    return [stats[t] for t in result_order]


def qualify_from_groups(
    group_results: dict[str, list[MatchResult]],
) -> tuple[dict[str, str], dict[str, str], list[tuple[str, TeamStats]]]:
    """Determine group winners, runners-up, and all 12 third-place finishers.

    Returns:
        winners:    {group_letter → team_name}
        runners_up: {group_letter → team_name}
        thirds:     [(group_letter, TeamStats), ...] — all 12 third-place teams
    """
    winners: dict[str, str] = {}
    runners_up: dict[str, str] = {}
    thirds: list[tuple[str, TeamStats]] = []

    for group, teams in GROUPS.items():
        results = group_results.get(group, [])
        ranked = rank_group(results, teams)
        winners[group] = ranked[0].team
        runners_up[group] = ranked[1].team
        thirds.append((group, ranked[2]))

    return winners, runners_up, thirds


def rank_third_place(thirds: list[tuple[str, TeamStats]]) -> list[tuple[str, str]]:
    """Rank all 12 third-place teams; return best 8 as [(group_letter, team_name)]."""

    def key(item: tuple[str, TeamStats]) -> tuple:
        s = item[1]
        return (s.points, s.gd, s.gf, random.random())

    ranked = sorted(thirds, key=key, reverse=True)
    return [(g, s.team) for g, s in ranked[:8]]
