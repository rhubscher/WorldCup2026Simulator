# Goal

 create a simulation app for the FIFA Soccer Worldchampionship 2026; the goal is to predict the outcome based on the teams' initial rating and their games at the championship so far

# Input

The pre tournament Fide rankings with there associate ratings for each team

The scores so far in the tournament


# Output

The expected rankings with the associated probabilities for each team


# the rules of the championship

two teams A, B play each other resulting in a score  a:b whee a are the number of goals scored by A, b by B. if a > b then A wins, if a = b, then this is a draw, and if a< b then B won.


# simulation

given the current state, run the rest of the turnament n times and compute the most expected outcome.



# 1) Groups and Teams

There are **12 groups (A–L), each with 4 teams (48 total)** [\[fifaworldcupnews.com\]](https://www.fifaworldcupnews.com/2026-fifa-world-cup-group-stage/)

```
Group A: Mexico, South Africa, Korea Republic, Czechia
Group B: Canada, Bosnia and Herzegovina, Qatar, Switzerland
Group C: Brazil, Morocco, Haiti, Scotland
Group D: USA, Paraguay, Australia, Türkiye
Group E: Germany, Curaçao, Côte d'Ivoire, Ecuador
Group F: Netherlands, Japan, Sweden, Tunisia
Group G: Belgium, Egypt, IR Iran, New Zealand
Group H: Spain, Cabo Verde, Saudi Arabia, Uruguay
Group I: France, Senegal, Iraq, Norway
Group J: Argentina, Algeria, Austria, Jordan
Group K: Portugal, DR Congo, Uzbekistan, Colombia
Group L: England, Croatia, Ghana, Panama
```

 [\[fifaworldcupnews.com\]](https://www.fifaworldcupnews.com/2026-fifa-world-cup-group-stage/)

***

# 2) Group Phase Ranking Rules

## Match structure

* Each group is **round-robin** (each team plays 3 matches) [\[futbolupdate.com\]](https://www.futbolupdate.com/2026-fifa-world-cup-group-stage-explained/)
* Points:
  * Win = 3
  * Draw = 1
  * Loss = 0 [\[worldcupma...chtime.com\]](https://www.worldcupmatchtime.com/en/standings)

## Ranking criteria (in order)

Teams in a group are ranked by:

1. Total points
2. Goal difference
3. Goals scored
4. Head-to-head results (between tied teams)
5. Fair play points (disciplinary record)
6. Drawing of lots [\[worldcupma...chtime.com\]](https://www.worldcupmatchtime.com/en/standings)

## Advancement from groups

* Top **2 teams per group** → qualify (24 teams)
* Plus **8 best third-place teams** across all groups → qualify
* Total advancing teams: **32** [\[worldcupwiki.com\]](https://worldcupwiki.com/teams/)

### Ranking of third-place teams

Across groups using:

1. Points
2. Goal difference
3. Goals scored
4. Fair play
5. (sometimes) FIFA ranking / drawing of lots    [\[worldcupwiki.com\]](https://worldcupwiki.com/2026-fifa-world-cup-round-of-32/)

***

# 3) Knockout Phase Structure

## Overview

* Starts with **Round of 32** (new for 2026) [\[worldcupwiki.com\]](https://worldcupwiki.com/teams/)
* Then:
  * Round of 32 → Round of 16 → Quarterfinals → Semifinals → Final
* Format: **single elimination** [\[en.wikipedia.org\]](https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage)

## Match rules

* If tied after 90 minutes:
  * Extra time (30 min)
  * Then penalties if needed [\[en.wikipedia.org\]](https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage)

***

# 4) Knockout Pairing Logic (Critical for Simulation)

## Inputs

* 12 group winners (1A–1L)
* 12 group runners-up (2A–2L)
* 8 qualified third-place teams (3X)

## Fixed structural rules

* Group winners **never play other group winners** in Round of 32 [\[worldcupwiki.com\]](https://worldcupwiki.com/2026-fifa-world-cup-round-of-32/)
* Third-place teams **only play group winners** [\[worldcupwiki.com\]](https://worldcupwiki.com/2026-fifa-world-cup-round-of-32/)
* Teams **cannot play a team from their own group** [\[worldcupwiki.com\]](https://worldcupwiki.com/2026-fifa-world-cup-round-of-32/)

## Pairing types

* Some matches are fixed (examples):
  * 2A vs 2B
  * 1F vs 2C
  * 1C vs 2F [\[snapbracket.com\]](https://snapbracket.com/guides/world-cup-2026-format)

* Others depend on:
  * Which 8 third-place teams qualify
  * Precomputed **495 possible bracket configurations** [\[worldcupwiki.com\]](https://worldcupwiki.com/2026-fifa-world-cup-round-of-32/)

👉 Therefore:

### Important implementation constraint

* The Round of 32 bracket is **not fully determined until all groups are completed**.
* You must:
  1. Rank third-place teams globally
  2. Select top 8
  3. Use a **mapping table (Annex C)** to assign matchups

***

# 5) Summary (Minimal Simulation Logic)

### Group phase

```
for each group:
  play round-robin (3 matches/team)
  compute standings using ranking criteria
```

### Qualification

```
qualifiers = []
for each group:
  add top 2 teams
collect 12 third-place teams
rank them globally
add top 8 third-place teams
```

### Knockout setup

```
inputs = winners (12), runners_up (12), best_third (8)
determine bracket using predefined mapping (dependent on which 3rd-place groups qualified)
```

### Knockout progression

```
single elimination:
  if draw -> extra time -> penalties
```

***

# Missing / Not Explicitly Defined

* Exact full Round-of-32 pairing table → **not fixed; defined by 495-case mapping (Annex C)**
* Exact head-to-head tie-break procedure details → **not fully enumerated in summarized sources**

***

If you want, I can convert the bracket logic into **explicit pseudocode + data structures for the 495-case mapping**, which is the only tricky part for implementation.
