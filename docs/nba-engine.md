# NBA implementation status

FanDuel NBA enters a separate route from NFL. The original nine-slot entry CSV
supplies IDs, positions, salaries and game pairs. Historical FPPG is not a
projection. DFF and RotoWire positive projections are averaged, uploaded CSV
values take priority (including exclusion by zero), and OUT players are ineligible.
RotoWire supplies projected minutes with exact date/game/slate guards.

## Numerical core

- Screenshot-verified FanDuel scoring: points + 1.2 rebounds + 1.5 assists +
  3 steals + 3 blocks - turnovers. Made threes are not counted twice.
- Experimental NumPy minutes sampler conserves 240 regulation team minutes,
  caps individuals at 48, and assigns unmodeled reserve minutes no fantasy points.
  Minute uncertainty and blowout flags are caller inputs, not fitted estimates.
- NumPy lineup scoring shares scenario/player outcomes across all lineups and
  processes bounded batches. Local synthetic benchmark: 5,000 nine-player
  lineups by 10,000 scenarios, 83 players, float32: 0.279 seconds. This excludes
  outcome generation, field ranking, I/O and hosted execution.

## Historical data

ESPN final-game PBP requires the game's date to precede the target slate and the
last event score to match the box score. Six games from October 21-22, 2025
preserved total points in initial possession reconstruction. This is a score
ledger check, not independent validation of every possession boundary.
Technical/retained-possession free throws, reviews and unclear control changes
are flagged, not silently treated as clean observations.

Rotation reconstruction uses box-score starters, substitutions and evidence of
participation before a first substitution. Unresolved initial lineups invalidate
the corresponding team-period. In the first test game, one overtime team-period
had only four identifiable starters and remains unresolved.

## Experimental forward events

`simmah_nba_engine.py` now simulates regulation using explicit five-player
rotations and caller-supplied event rates. Made field goals generate scoring and
optional non-self assists. Misses create rebound opportunities and possible
blocks. Turnovers create possible steals. Offensive rebounds retain possession.
Free throw trips distinguish final missed attempts from earlier dead-ball misses.
NumPy batches scenarios while the event loop advances shared game clocks.

A synthetic 10,000-game regulation benchmark took 1.673 seconds locally. This
uses equal role weights and illustrative rates, not trained NBA parameters. It
excludes model fitting, rotation generation, overtime and contest evaluation.
Regulation ties are explicitly marked `requires_overtime`; they are not final
game outcomes. Per-player shooting efficiency, quarter-end logic, fouls and
coaching decisions need further development.

## Not ready for builds

The forward core, fitted event rates, calibrated rotation or injury probabilities,
NBA opponent model, portfolio evaluation and entry export are not connected yet. The NBA BUILD button remains disabled. Next work must validate
rotations and possession reconstruction broadly, fit historical rates without
lookahead, then implement and test shared forward events and legal lineups.
