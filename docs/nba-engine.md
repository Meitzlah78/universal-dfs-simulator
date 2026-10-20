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

`simmah_nba_engine.py` now simulates quarters and optional overtime using explicit five-player
rotations and caller-supplied event rates. Made field goals generate scoring and
optional non-self assists. Misses create rebound opportunities and possible
blocks. Turnovers create possible steals. Offensive rebounds retain possession.
Free throw trips distinguish final missed attempts from earlier dead-ball misses.
NumPy batches scenarios while the event loop advances shared game clocks.

A synthetic 10,000-game regulation benchmark took 1.673 seconds locally. This
uses equal role weights and illustrative rates, not trained NBA parameters. It
excludes model fitting, rotation generation, overtime and contest evaluation.
Regulation ties require explicit overtime rotations. Ties remaining after the
supplied overtime periods are marked `requires_overtime`; they are not final
game outcomes. Period-crossing actions are discarded at the boundary. Individual
shooting efficiency, fouls and coaching decisions need further development.

NBA roster validation and an offline entry export helper now preserve the
nine-slot header and original entry/player IDs. The helper requires an explicit team limit. FanDuel rules at
https://www.fanduel.com/rules (Lineup Restrictions, checked October 20, 2026)
require at least three teams and no more than four players per team for most
multi-game contests. The NBA validator now also enforces the three-team minimum.
These helpers remain disconnected from the live BUILD/export interface.

## Not ready for builds

The forward core, fitted event rates, calibrated rotation or injury probabilities,
NBA opponent model, portfolio evaluation and entry export are not connected yet. The NBA BUILD button remains disabled. Next work must validate
rotations and possession reconstruction broadly, fit historical rates without
lookahead, then implement and test shared forward events and legal lineups.

## Preliminary historical fit

`simmah_nba_fit.fit_baseline` estimates pooled event rates from pre-slate team box
scores, with unique-game and date guards. Its default minimum is 30 games. An
explicit exploratory override on six October 21-22, 2025 games produced 14.24%
turnovers per modeled action, 41.98% three-point attempt share, 57.56% two-point
shooting, 34.00% three-point shooting, and 79.28% free throws. These observations
are not season-wide estimates or an out-of-sample validation. FTA/2 is an
approximation to trips; team/personal turnovers and player-specific efficiencies
remain unresolved. This fit cannot by itself enable NBA builds.

### Expanded historical audit

The offline audit of April 1–10, 2026 requested 70 completed games.
One game (401810990) failed the official final-score check and was excluded.
The remaining 69 games split chronologically into 59 fitting games and 10 held-out
games beginning April 9. All 69 reconstructed score ledgers matched final totals;
67 had complete rotation reconstruction. Incomplete rotations remain flagged.
This is a source/reconstruction audit, not evidence of predictive accuracy.
The fitted rates are experimental and are not installed as live build defaults.

Reproduce with:
```sh
python scripts/nba_history_check.py --start 2026-04-01 --end 2026-04-10 --before 2026-10-20 --cache /tmp/simmah-nba-corpus --output /tmp/nba-corpus-audit.json --limit 70 --holdout 8
```

Player allocation rates now use historical FGA, AST, REB, STL and BLK per minute,
shrunk toward pooled rates with a fixed 120-minute prior. ESPN player IDs retain
identity across team changes. The audit's 59 training games yielded 434 players;
215 held-out player-games included 211 with fitted player history.
Conditional on actual minutes, player/pooled MAE was 2.325/2.634 FGA,
1.429/1.610 AST, 1.722/2.055 REB, .714/.721 STL and .503/.532 BLK.
These are allocation diagnostics, not fantasy-point or pregame-minute accuracy.
The role model is offline and has not been connected to live NBA builds.

### Minutes baseline check

A frozen chronological baseline used each player's last three regulation games
from the same 59-game training set. On 152 covered held-out player-games, minutes
MAE was 5.743, RMSE 7.239 and bias -0.629 minutes. The full-training mean baseline
had MAE 5.783. Another 63 player-games lacked three historical observations.
Overtime is excluded from this regulation-only diagnostic. Holdout results never
update the fitting history. This conditions on participation and cannot measure
DNP risk, pregame injury information, or redistribution after scratches.
Consequently recent averages do not replace RotoWire's pregame projected minutes.
Historical uncertainty calibration still requires a larger sample and a separate
validation set before any tuned uncertainty model enters live builds.
