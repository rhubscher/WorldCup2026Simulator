# FIFA World Cup 2026 — Monte Carlo Simulator

A Python toolkit that simulates the 2026 FIFA World Cup and estimates each team's probability of advancing through every knockout round.

Match outcomes are modelled with Glicko-2 ratings (win/draw/loss probabilities) and Poisson-distributed scorelines. The simulator covers the full tournament: 12 group stages, a 48-team bracket with third-place qualification, through to the final. Completed match results are fed in from `data/scores.csv` and ratings are updated before each simulation run.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
```

## Scripts

| Script | What it does |
|---|---|
| `main.py` | Run N simulated tournaments; print each team's round-reach probabilities |
| `visualize.py` | Heatmap of round-reach probabilities (reads JSON from `main.py`) |
| `matchup.py` | Head-to-head scoreline distribution for any two teams, or all of today's fixtures |
| `next_opponents.py` | Probable next-round opponents with conditional probabilities |
| `pairings.py` | Current knockout bracket derived from completed results (no simulation) |
| `update_scores.py` | Pull latest results from ESPN and update `data/scores.csv` |
| `surprises.py` | Rank completed matches by how unlikely the actual outcome was |
| `rating_changes.py` | Teams over/underperforming their pre-tournament Glicko-2 baseline |
| `timeline.py` | Line chart of each team's simulated ranking across match days |

### Key examples

```powershell
# Run 10 000 simulations (default)
uv run main.py

# Pipe into heatmap
uv run main.py -n 1000 --output json | uv run visualize.py --save chart.png

# Head-to-head
uv run matchup.py France Argentina

# Predict today's matches
uv run matchup.py --today

# Probable next opponents
uv run next_opponents.py --team Germany

# Fetch latest scores
uv run update_scores.py --days 3
```

See `usage.txt` for the full option reference for every script.

## Data

| File | Contents |
|---|---|
| `data/ratings.csv` | 48 teams with Glicko-2 rating, RD, and volatility |
| `data/scores.csv` | Completed match results (phase, teams, goals, AET/penalties, date) |

## Architecture

Flat `src/` module layout: `data.py` → `ratings.py` → `match.py` → `tournament.py` → `bracket.py` → `simulation.py` → `output.py`. See `CLAUDE.md` for details.
