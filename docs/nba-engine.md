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

## Not ready for builds

No forward NBA possession simulator, fitted event rates, calibrated rotation or
injury probabilities, NBA opponent model, portfolio evaluation or entry export is
connected yet. The NBA BUILD button remains disabled. Next work must validate
rotations and possession reconstruction broadly, fit historical rates without
lookahead, then implement and test shared forward events and legal lineups.
