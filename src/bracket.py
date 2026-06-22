from __future__ import annotations

# Round of 32 match slots and their allowed third-place groups.
# Each entry: match_number → (winner_slot, optional_runner_up_slot, allowed_3rd_groups)
# For slots without a third-place team, allowed_3rd_groups is None.

# Fixed pairings (runners-up or specific winner vs runner-up)
_FIXED_R32: list[tuple[str, str]] = [
    ("2A", "2B"),   # M73
    ("1E", None),   # M74 — third-place slot
    ("1F", "2C"),   # M75
    ("1C", "2F"),   # M76
    ("1I", None),   # M77 — third-place slot
    ("2E", "2I"),   # M78
    ("1A", None),   # M79 — third-place slot
    ("1L", None),   # M80 — third-place slot
    ("1D", None),   # M81 — third-place slot
    ("1G", None),   # M82 — third-place slot
    ("2K", "2L"),   # M83
    ("1H", "2J"),   # M84
    ("1B", None),   # M85 — third-place slot
    ("1J", "2H"),   # M86
    ("1K", None),   # M87 — third-place slot
    ("2D", "2G"),   # M88
]

# For each third-place slot (identified by winner slot), which groups are allowed.
# These are the groups from which the qualifying third-place team may come.
_THIRD_PLACE_ALLOWED: dict[str, set[str]] = {
    "1E": {"A", "B", "C", "D", "F"},   # M74
    "1I": {"C", "D", "F", "G", "H"},   # M77
    "1A": {"C", "E", "F", "H", "I"},   # M79
    "1L": {"E", "H", "I", "J", "K"},   # M80
    "1D": {"B", "E", "F", "I", "J"},   # M81
    "1G": {"A", "E", "H", "I", "J"},   # M82
    "1B": {"E", "F", "G", "I", "J"},   # M85
    "1K": {"D", "E", "I", "J", "L"},   # M87
}

# Round of 16 bracket: each pair is (r32_match_index_a, r32_match_index_b)
# r32_match_index is 0-based index into the 16 R32 matches above.
_R16_PAIRS: list[tuple[int, int]] = [
    (0, 2),   # W73 vs W75 → M89
    (1, 4),   # W74 vs W77 → M90
    (3, 5),   # W76 vs W78 → M91  (index 3=M76 after reordering... wait)
    (6, 7),   # W79 vs W80 → M92
    (10, 11), # W83 vs W84 → M93
    (8, 9),   # W81 vs W82 → M94
    (13, 15), # W86 vs W88 → M95
    (12, 14), # W85 vs W87 → M96
]

# Quarterfinal bracket: each pair is (r16_match_index_a, r16_match_index_b)
_QF_PAIRS: list[tuple[int, int]] = [
    (0, 1),  # W89 vs W90 → M97
    (4, 5),  # W93 vs W94 → M98
    (2, 3),  # W91 vs W92 → M99
    (6, 7),  # W95 vs W96 → M100
]

# Semifinal bracket: each pair is (qf_match_index_a, qf_match_index_b)
_SF_PAIRS: list[tuple[int, int]] = [
    (0, 1),  # W97 vs W98 → M101
    (2, 3),  # W99 vs W100 → M102
]


def _assign_third_place(
    qualifying_groups: list[str],
) -> dict[str, str]:
    """Backtracking assignment of qualifying third-place groups to match slots.

    Returns {winner_slot → group_letter} for each of the 8 third-place slots.
    qualifying_groups: the 8 group letters whose third-place team qualified.
    """
    slots = list(_THIRD_PLACE_ALLOWED.keys())
    qualifying_set = set(qualifying_groups)
    assignment: dict[str, str] = {}
    used: set[str] = set()

    def backtrack(idx: int) -> bool:
        if idx == len(slots):
            return True
        slot = slots[idx]
        allowed = _THIRD_PLACE_ALLOWED[slot]
        # Sort candidates for determinism (most-constrained first would be better,
        # but simple alphabetical is fine for simulation purposes)
        candidates = sorted(qualifying_set & allowed - used)
        for group in candidates:
            assignment[slot] = group
            used.add(group)
            if backtrack(idx + 1):
                return True
            del assignment[slot]
            used.remove(group)
        return False

    if not backtrack(0):
        raise ValueError(
            f"No valid third-place assignment found for qualifying groups: {qualifying_groups}"
        )
    return assignment


def build_r32_bracket(
    winners: dict[str, str],      # group → team name
    runners_up: dict[str, str],   # group → team name
    best_8_thirds: list[tuple[str, str]],  # [(group, team_name), ...] best-to-worst
) -> list[tuple[str, str]]:
    """Build the 16 Round-of-32 matchups as (team_a, team_b) pairs."""
    third_group_to_team: dict[str, str] = {g: t for g, t in best_8_thirds}
    qualifying_groups = [g for g, _ in best_8_thirds]
    third_assignment = _assign_third_place(qualifying_groups)

    def resolve(slot: str) -> str:
        if slot[0] == "1":
            return winners[slot[1]]
        if slot[0] == "2":
            return runners_up[slot[1]]
        raise ValueError(f"Unexpected slot format: {slot}")

    matchups: list[tuple[str, str]] = []
    for winner_slot, other_slot in _FIXED_R32:
        team_a = resolve(winner_slot)
        if other_slot is None:
            group = third_assignment[winner_slot]
            team_b = third_group_to_team[group]
        else:
            team_b = resolve(other_slot)
        matchups.append((team_a, team_b))

    return matchups
