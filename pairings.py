from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from src.bracket import (
    _FIXED_R32,
    _R16_PAIRS,
    _QF_PAIRS,
    _SF_PAIRS,
    _assign_third_place,
)
from src.data import GROUPS, load_ratings, load_scores
from src.ratings import get_probabilities, update_ratings
from src.tournament import _h2h_gd_among, _h2h_gf_among, _h2h_points_among

R32_NUMS = list(range(73, 89))
R16_NUMS = list(range(89, 97))
QF_NUMS = list(range(97, 101))
SF_NUMS = [101, 102]
FINAL_NUM = 103


def _stats(results, teams):
    s = {t: [0, 0, 0] for t in teams}  # [pts, gd, gf]
    for r in results:
        if r.team_a not in s or r.team_b not in s:
            continue
        d = r.goals_a - r.goals_b
        s[r.team_a][1] += d
        s[r.team_b][1] -= d
        s[r.team_a][2] += r.goals_a
        s[r.team_b][2] += r.goals_b
        if d > 0:
            s[r.team_a][0] += 3
        elif d == 0:
            s[r.team_a][0] += 1
            s[r.team_b][0] += 1
        else:
            s[r.team_b][0] += 3
    return {t: tuple(v) for t, v in s.items()}


def _rank_cluster(cluster: list[str], st: dict, results) -> list[str | None]:
    """Recursively rank a tied-on-points cluster.

    Tiebreaker order: H2H pts → H2H GD → H2H GF → overall GD → overall GF.
    H2H is recomputed for each remaining subgroup (FIFA rule).
    Returns None for positions unresolvable without fair play / FIFA ranking.
    """
    h_pts = _h2h_points_among(cluster, results)
    h_gd = _h2h_gd_among(cluster, results)
    h_gf = _h2h_gf_among(cluster, results)

    def hk(t: str) -> tuple:
        return (h_pts[t], h_gd[t], h_gf[t], st[t][1], st[t][2])

    by_criteria = sorted(cluster, key=hk, reverse=True)
    output: list[str | None] = []
    ii = 0
    while ii < len(by_criteria):
        jj = ii + 1
        while jj < len(by_criteria) and hk(by_criteria[jj]) == hk(by_criteria[ii]):
            jj += 1
        sub = by_criteria[ii:jj]
        if len(sub) == 1:
            output.extend(sub)
        elif len(sub) < len(cluster):
            output.extend(_rank_cluster(sub, st, results))
        else:
            output.extend([None] * len(sub))
        ii = jj
    return output


def _rank_deterministic(results, teams) -> list[str | None]:
    """Rank 4 teams without random tiebreaking.

    Returns a 4-slot list; None at a position means that slot is unresolvable
    from match data alone (fair play / FIFA ranking required).
    """
    st = _stats(results, teams)
    # Primary sort: points only
    by_pts = sorted(teams, key=lambda t: st[t][0], reverse=True)

    output: list[str | None] = []
    i = 0
    while i < len(by_pts):
        j = i + 1
        while j < len(by_pts) and st[by_pts[j]][0] == st[by_pts[i]][0]:
            j += 1
        cluster = by_pts[i:j]
        if len(cluster) == 1:
            output.extend(cluster)
        else:
            output.extend(_rank_cluster(cluster, st, results))
        i = j

    return output


def _ko_winner(results, ta, tb):
    for r in results:
        if {r.team_a, r.team_b} == {ta, tb}:
            return r.winner()
    return None


def _prob_str(ta: str, tb: str, ratings: dict) -> str:
    if ta not in ratings or tb not in ratings:
        return ""
    p_win, p_draw, p_loss = get_probabilities(ratings[ta], ratings[tb])
    return f" :: {p_win:.0%} / {p_draw:.0%} / {p_loss:.0%}"


def main(scores_path: str = "data/scores.csv", ratings_path: str = "data/ratings.csv"):
    scores = load_scores(scores_path)
    ratings = update_ratings(load_ratings(ratings_path), scores)

    grp = {g: [] for g in GROUPS}
    ko: dict[str, list] = {ph: [] for ph in ("r32", "r16", "qf", "sf", "final")}
    for r in scores:
        if r.phase == "group" and r.group in GROUPS:
            grp[r.group].append(r)
        elif r.phase in ko:
            ko[r.phase].append(r)

    confirmed: dict[str, list] = defaultdict(list)  # phase -> [(label, ta, tb)]

    # ── Group stage ──────────────────────────────────────────────────────────
    for g, teams in GROUPS.items():
        played = {frozenset([r.team_a, r.team_b]) for r in grp[g]}
        for a, b in combinations(teams, 2):
            if frozenset([a, b]) not in played:
                confirmed["group"].append((f"Group {g}", a, b))

    # ── Group standings ───────────────────────────────────────────────────────
    done = {g: len(grp[g]) == 6 for g in GROUPS}
    ranking: dict[str, list[str | None] | None] = {
        g: (_rank_deterministic(grp[g], GROUPS[g]) if done[g] else None) for g in GROUPS
    }

    def team_at(g: str, p: int) -> str | None:
        if not done[g]:
            return None
        r = ranking[g]
        return r[p] if r else None  # r[p] itself may be None if ambiguous

    # ── Wildcard (3rd-place) slot resolution ─────────────────────────────────
    wildcard: dict[str, str] = {}  # winner_slot -> team_name

    if all(done.values()):
        thirds = {g: team_at(g, 2) for g in GROUPS}
        if all(t is not None for t in thirds.values()):
            third_st = {g: _stats(grp[g], GROUPS[g])[thirds[g]] for g in GROUPS}
            ranked_thirds = sorted(
                GROUPS.keys(), key=lambda g: third_st[g], reverse=True
            )

            # Confirm only if the 8th/9th boundary is unambiguous
            if third_st[ranked_thirds[7]] != third_st[ranked_thirds[8]]:
                qualifying = ranked_thirds[:8]
                try:
                    assignment = _assign_third_place(qualifying)
                    wildcard = {slot: thirds[gl] for slot, gl in assignment.items()}
                except ValueError:
                    pass

    # ── Round of 32 ──────────────────────────────────────────────────────────
    r32_pairs: list[tuple[str | None, str | None]] = []

    for ws, os_ in _FIXED_R32:
        ta = team_at(ws[1], 0 if ws[0] == "1" else 1)
        if os_ is None:
            tb = wildcard.get(ws)
        elif os_[0] == "1":
            tb = team_at(os_[1], 0)
        else:
            tb = team_at(os_[1], 1)
        r32_pairs.append((ta, tb))

    played_r32 = {frozenset([r.team_a, r.team_b]) for r in ko["r32"]}
    for idx, (ta, tb) in enumerate(r32_pairs):
        if ta and tb and frozenset([ta, tb]) not in played_r32:
            confirmed["r32"].append((f"M{R32_NUMS[idx]}", ta, tb))

    # ── Round of 16 ──────────────────────────────────────────────────────────
    r32_w = [
        (_ko_winner(ko["r32"], ta, tb) if (ta and tb) else None) for ta, tb in r32_pairs
    ]

    played_r16 = {frozenset([r.team_a, r.team_b]) for r in ko["r16"]}
    r16_pairs: list[tuple[str | None, str | None]] = []
    for idx, (ia, ib) in enumerate(_R16_PAIRS):
        wa, wb = r32_w[ia], r32_w[ib]
        r16_pairs.append((wa, wb))
        if wa and wb and frozenset([wa, wb]) not in played_r16:
            confirmed["r16"].append((f"M{R16_NUMS[idx]}", wa, wb))

    # ── Quarterfinals ────────────────────────────────────────────────────────
    r16_w = [
        (_ko_winner(ko["r16"], ta, tb) if (ta and tb) else None) for ta, tb in r16_pairs
    ]

    played_qf = {frozenset([r.team_a, r.team_b]) for r in ko["qf"]}
    qf_pairs: list[tuple[str | None, str | None]] = []
    for idx, (ia, ib) in enumerate(_QF_PAIRS):
        wa, wb = r16_w[ia], r16_w[ib]
        qf_pairs.append((wa, wb))
        if wa and wb and frozenset([wa, wb]) not in played_qf:
            confirmed["qf"].append((f"M{QF_NUMS[idx]}", wa, wb))

    # ── Semifinals ───────────────────────────────────────────────────────────
    qf_w = [
        (_ko_winner(ko["qf"], ta, tb) if (ta and tb) else None) for ta, tb in qf_pairs
    ]

    played_sf = {frozenset([r.team_a, r.team_b]) for r in ko["sf"]}
    sf_pairs: list[tuple[str | None, str | None]] = []
    for idx, (ia, ib) in enumerate(_SF_PAIRS):
        wa, wb = qf_w[ia], qf_w[ib]
        sf_pairs.append((wa, wb))
        if wa and wb and frozenset([wa, wb]) not in played_sf:
            confirmed["sf"].append((f"M{SF_NUMS[idx]}", wa, wb))

    # ── Final ────────────────────────────────────────────────────────────────
    sf_w = [
        (_ko_winner(ko["sf"], ta, tb) if (ta and tb) else None) for ta, tb in sf_pairs
    ]
    played_final = {frozenset([r.team_a, r.team_b]) for r in ko["final"]}
    if len(sf_w) == 2 and all(sf_w):
        ta, tb = sf_w[0], sf_w[1]
        if frozenset([ta, tb]) not in played_final:
            confirmed["final"].append((f"M{FINAL_NUM}", ta, tb))

    # ── Output ───────────────────────────────────────────────────────────────
    phase_labels = {
        "group": "Group Stage",
        "r32": "Round of 32",
        "r16": "Round of 16",
        "qf": "Quarterfinals",
        "sf": "Semifinals",
        "final": "Final",
    }

    total = 0
    for phase in ("group", "r32", "r16", "qf", "sf", "final"):
        games = confirmed[phase]
        if not games:
            continue
        print(f"\n=== {phase_labels[phase]} ({len(games)} confirmed) ===")
        if phase == "group":
            by_group: dict[str, list] = defaultdict(list)
            for label, ta, tb in games:
                by_group[label].append((ta, tb))
            for glabel in sorted(by_group):
                print(f"  {glabel}:")
                for ta, tb in by_group[glabel]:
                    print(f"    {ta} vs {tb}{_prob_str(ta, tb, ratings)}")
        else:
            for label, ta, tb in games:
                print(f"  {label}: {ta} vs {tb}{_prob_str(ta, tb, ratings)}")
        total += len(games)

    print(f"\nTotal: {total} confirmed unplayed pairings")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--scores", default="data/scores.csv")
    args = p.parse_args()
    main(args.scores)
