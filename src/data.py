from __future__ import annotations

import csv
from dataclasses import dataclass

GROUPS: dict[str, list[str]] = {
    "A": ["Mexico", "South Africa", "Korea Republic", "Czechia"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["USA", "Paraguay", "Australia", "Turkey"],
    "E": ["Germany", "Curacao", "Cote d'Ivoire", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "IR Iran", "New Zealand"],
    "H": ["Spain", "Cabo Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

TEAM_TO_GROUP: dict[str, str] = {
    team: group for group, teams in GROUPS.items() for team in teams
}

VALID_PHASES = {"group", "r32", "r16", "qf", "sf", "final"}


@dataclass
class TeamRating:
    team: str
    rating: float
    rd: float
    volatility: float


@dataclass
class MatchResult:
    phase: str
    group: str
    team_a: str
    team_b: str
    goals_a: int
    goals_b: int
    aet: bool
    penalties_a: int | None
    penalties_b: int | None
    date: str | None = None

    def winner(self) -> str:
        if self.penalties_a is not None:
            return self.team_a if self.penalties_a > self.penalties_b else self.team_b
        return self.team_a if self.goals_a > self.goals_b else self.team_b

    def is_draw(self) -> bool:
        return self.goals_a == self.goals_b and self.penalties_a is None


def load_ratings(path: str) -> dict[str, TeamRating]:
    ratings: dict[str, TeamRating] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            team = row["team"].strip()
            ratings[team] = TeamRating(
                team=team,
                rating=float(row["rating"]),
                rd=float(row["rd"]),
                volatility=float(row["volatility"]),
            )
    missing = set(TEAM_TO_GROUP) - set(ratings)
    if missing:
        raise ValueError(f"Ratings file is missing teams: {sorted(missing)}")
    return ratings


def load_scores(path: str) -> list[MatchResult]:
    results: list[MatchResult] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            phase = row["phase"].strip()
            if phase not in VALID_PHASES:
                raise ValueError(f"Row {row_num}: unknown phase '{phase}'")

            team_a = row["team_a"].strip()
            team_b = row["team_b"].strip()
            if team_a not in TEAM_TO_GROUP:
                raise ValueError(f"Row {row_num}: unknown team '{team_a}' in team_a")
            if team_b not in TEAM_TO_GROUP:
                raise ValueError(f"Row {row_num}: unknown team '{team_b}' in team_b")

            group = row.get("group", "").strip()
            if phase == "group":
                if group not in GROUPS:
                    raise ValueError(f"Row {row_num}: unknown group '{group}'")
                if team_a not in GROUPS[group]:
                    raise ValueError(
                        f"Row {row_num}: '{team_a}' is not in group {group}"
                    )
                if team_b not in GROUPS[group]:
                    raise ValueError(
                        f"Row {row_num}: '{team_b}' is not in group {group}"
                    )

            goals_a_raw = row.get("goals_a", "").strip()
            goals_b_raw = row.get("goals_b", "").strip()
            if not goals_a_raw or not goals_b_raw:
                continue  # pairing entered but match not yet played
            try:
                goals_a = int(goals_a_raw)
                goals_b = int(goals_b_raw)
            except ValueError as exc:
                raise ValueError(f"Row {row_num}: invalid goals — {exc}") from exc

            pen_a_raw = row.get("penalties_a", "").strip()
            pen_b_raw = row.get("penalties_b", "").strip()
            try:
                penalties_a = int(pen_a_raw) if pen_a_raw else None
                penalties_b = int(pen_b_raw) if pen_b_raw else None
            except ValueError as exc:
                raise ValueError(f"Row {row_num}: invalid penalties — {exc}") from exc

            if penalties_a is not None and penalties_b is not None:
                goals_a += penalties_a
                goals_b += penalties_b

            results.append(
                MatchResult(
                    phase=phase,
                    group=group,
                    team_a=team_a,
                    team_b=team_b,
                    goals_a=goals_a,
                    goals_b=goals_b,
                    aet=row.get("aet", "").strip().lower() in ("true", "1", "yes"),
                    penalties_a=penalties_a,
                    penalties_b=penalties_b,
                    date=row.get("date", "").strip() or None,
                )
            )
    return results
