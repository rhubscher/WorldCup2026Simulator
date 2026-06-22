# Product Requirements Document — FIFA World Cup 2026 Simulator

## 1. Purpose

A CLI tool that simulates the remaining games of the 2026 FIFA World Cup, given the current state of the tournament, and outputs the probability of each team winning the championship, reaching each round, finishing in each group position, and the single most-likely full bracket.

---

## 2. Goals

| # | Goal |
|---|------|
| G1 | Ingest pre-tournament Glicko-2 ratings and any completed match results as input |
| G2 | Simulate the remaining tournament N times using a Glicko-2–based soccer match model |
| G3 | Output four views of the simulation results (see §5) |
| G4 | Implement the full FIFA 495-case Round-of-32 bracket mapping |

---

## 3. Non-Goals

- No web UI, API server, or notebook interface
- No live data fetching — all input is file-based
- No historical back-testing or model training — ratings are provided as input
- No league or club match simulation beyond the WC tournament itself

---

## 4. Inputs

### 4.1 Pre-tournament ratings file (`--ratings`)

CSV file with one row per team. Required columns:

| Column | Type | Description |
|--------|------|-------------|
| `team` | string | Team name exactly matching the groups definition |
| `rating` | float | Glicko-2 rating (default scale: 1500) |
| `rd` | float | Rating deviation (uncertainty; default 350) |
| `volatility` | float | Volatility σ (default 0.06) |

### 4.2 Completed matches file (`--scores`)

CSV file with one row per completed match. Can be empty (simulates full tournament from scratch). Required columns:

| Column | Type | Description |
|--------|------|-------------|
| `phase` | string | `group`, `r32`, `r16`, `qf`, `sf`, `final` |
| `group` | string | Group letter A–L (group phase only; leave blank otherwise) |
| `team_a` | string | Team name |
| `team_b` | string | Team name |
| `goals_a` | int | Goals scored by team_a (regular time) |
| `goals_b` | int | Goals scored by team_b (regular time) |
| `aet` | bool | True if match went to extra time |
| `penalties_a` | int | Penalty goals (knockout only; blank if not applicable) |
| `penalties_b` | int | Penalty goals (knockout only; blank if not applicable) |

### 4.3 CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--ratings FILE` | `data/ratings.csv` | Path to ratings CSV |
| `--scores FILE` | `data/scores.csv` | Path to completed scores CSV |
| `--simulations N` / `-n N` | `10000` | Number of Monte Carlo simulation runs |
| `--output FORMAT` | `text` | Output format: `text` or `json` |

---

## 5. Outputs

All four views are printed to stdout on every run (or written as a JSON object when `--output json`).

### 5.1 Tournament winner odds
Probability (%) that each team wins the championship. Sorted descending.

```
Tournament winner probabilities:
  1. Brazil          18.4%
  2. France          14.1%
  ...
```

### 5.2 Round-by-round reach probabilities
For each team: probability of reaching each knockout round (R32, R16, QF, SF, Final, Win).

```
Round-by-round probabilities:
Team             R32    R16    QF     SF    Final   Win
Brazil          94.1%  78.2%  55.0%  38.1%  24.0%  18.4%
...
```

### 5.3 Group standings
For each group: expected final position (1st–4th) distribution for each team, plus the most likely final group table.

```
Group A — most likely standings:
  1. Mexico          (1st: 52%, 2nd: 30%, 3rd: 15%, 4th: 3%)
  ...
```

### 5.4 Most-likely bracket
The single bracket (path of winners) that appeared most frequently across all simulations. Printed as a tree.

---

## 6. Simulation Model

### 6.1 Rating updates from completed matches

After loading completed match results, update each team's Glicko-2 parameters using the **GlickoSoccer** implementation ([andreyshelopugin/GlickoSoccer](https://github.com/andreyshelopugin/GlickoSoccer)). This accounts for the draw probability and goal margin.

### 6.2 Match outcome sampling

For each simulated match, derive win/draw/loss probabilities from the two teams' current Glicko-2 ratings via the GlickoSoccer model, then sample one outcome. No home-field advantage is applied (all matches are at neutral venues).

- **Group phase**: draw is a valid outcome → record goals, update points table.
- **Knockout phase**: draw after 90 min → simulate extra time → if still level, penalty shootout (see §6.3).

**Goal simulation (group phase):** Scorelines are sampled using independent Poisson distributions:

```
goals_A ~ Poisson(λ_A),  goals_B ~ Poisson(λ_B)
```

Expected goals are derived from a fixed baseline and the teams' win probability:

```
base_λ  = 1.3   # average goals per team in an even match
p_win_A = win probability for team A from Glicko-2
λ_A = base_λ * (1 + k * (p_win_A - 0.5))
λ_B = base_λ * (1 + k * (p_win_B - 0.5))   # p_win_B = 1 - p_win_A - p_draw
```

The scaling constant `k` is a single tunable parameter (starting value: `k = 1.0`). Scorelines are resampled if the result direction contradicts the sampled outcome (e.g. Poisson draw when "win" was sampled), to keep the goal model consistent with the match result.

Knockout-phase matches do not require scorelines beyond determining a winner; only the result (win/loss after 90 min, AET, or penalties) is tracked.

### 6.3 Penalty shootout

Modeled as a flat 50/50 coin flip per match. Whichever team wins the coin flip advances.

### 6.4 Rating updates mid-simulation

Within a single simulation run, ratings are **not** updated as simulated matches are played. Each simulated match uses the ratings derived from actual completed results only. This keeps runs independent and consistent.

---

## 7. Tournament Structure (Simulation-Relevant Rules)

### 7.1 Group phase

- 12 groups (A–L), 4 teams each, round-robin (3 matches per team).
- Points: Win = 3, Draw = 1, Loss = 0.
- Group ranking tiebreakers (in order):
  1. Total points
  2. Goal difference
  3. Goals scored
  4. Head-to-head results between tied teams
  5. Fair play points *(see assumption A3)*
  6. Drawing of lots *(simulated as random)*

### 7.2 Qualification to knockout phase

- Top 2 teams from each group → 24 teams.
- Best 8 third-place finishers across all groups → 8 teams.
- Third-place ranking criteria: points → goal difference → goals scored → fair play → drawing of lots.
- Total: 32 teams advance.

### 7.3 Round of 32 bracket

The matchup table depends on which 8 of the 12 third-place teams qualify. FIFA defines **495 possible configurations** (Annex C of the official regulations). The tool must implement this lookup table in full.

Fixed pairings (examples from the official bracket): 2A vs 2B, 1F vs 2C, 1C vs 2F. The remaining pairings involving third-place teams vary by configuration.

### 7.4 Knockout progression

Round of 32 → Round of 16 → Quarterfinals → Semifinals → Final. Single elimination. Losers are eliminated; no third-place playoff is in scope (see §3).

---

## 8. Architecture (High Level)

```
main.py
├── cli.py          — argument parsing, top-level orchestration
├── data.py         — load/validate ratings CSV and scores CSV
├── ratings.py      — Glicko-2 update logic (wraps GlickoSoccer)
├── tournament.py   — group standings, qualification, bracket assembly
├── bracket.py      — 495-case Round-of-32 mapping table
├── simulation.py   — Monte Carlo engine (runs N simulations)
├── match.py        — single-match outcome sampler
└── output.py       — text and JSON formatters
```

---

## 9. Assumptions & Decisions

| # | Decision |
|---|----------|
| A1 | All 48 teams' pre-tournament ratings are provided by the user; the tool does not fetch or compute them. |
| A2 | Neutral venue — no home-field advantage is applied in any match. |
| A3 | Fair play tiebreaker is treated as equal for all teams (effectively skipped); ties resolved by random draw. |
| A4 | No third-place playoff match is simulated. |
| A5 | Extra time is modeled as an independent additional match segment using the same rating-based probabilities (not a continuation of the 90-min score). |
| A6 | Penalty shootouts are 50/50 coin flips — no rating advantage. |
| A7 | Goal simulation uses the simple Poisson scaling rule (§6.2) with `base_λ = 1.3` and `k = 1.0`. |
| A8 | Ratings are updated only from actual completed matches, never from simulated ones. Each simulation run starts from the same post-actuals state. |
| A9 | Partial tournament states are supported: the scores file may contain results from any phase (group, r32, r16, qf, sf). The simulator picks up from wherever results end. |
