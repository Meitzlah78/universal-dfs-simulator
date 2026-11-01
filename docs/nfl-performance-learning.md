# Automatic NFL performance learning

## What runs

The daily completed-game workflow refreshes complete regular-season weeks from
nflverse. Published schedule scores, exact scheduled-game coverage and PBP
regulation-end markers must agree. A feed failure is recorded explicitly and
uses existing saved archives when available; it does not stop useful learning
from those games or fabricate new results.

The automatic component learner uses three chronological whole-week blocks:
earlier training games, a later selection week, and another later validation
week. Different components have independent data requirements. Missing kick
results or fumble flags do not block validated rushing/receiving components.

Supported automatic components are pass/run propensity, sacks, interceptions,
completions, fumble losses, extra points, two-point choice and success,
turnover-return TD probability, distance-conditioned field-goal accuracy,
receiving-yard spread, and rushing spread/tail family. Mean/role corrections and
joint-game dependence still use the broader full-game replay path below; their
pending status is not presented as an active improvement.

Every accepted component must improve on the selection week and on the final
week. Final checks use game-cluster bootstraps and a familywise-adjusted upper
loss-change bound plus a minimum 0.2% gain. Distribution changes must also pass
combined tail Brier checks (10+/20+ rushing yards, 20+/40+ receiving yards). The
fitter never reads final-week outcomes. Final weeks are recorded in a consumed
block ledger and cannot be repeatedly retested against successive incumbents.
These are retrospective historical tests: protocol development and published
stat corrections prevent claiming a prospective trial.

## First actual update from existing saved games

Week 5: 15 training games. Week 6: 14 selection games. Week 7: 14 validation games.
The rushing family changes from a normal per-carry draw with SD 5.5 to a
variance-standardized Student-t draw with 3 degrees of freedom and SD parameter
6.0, before the existing physical clips and shared stat accounting.

The held-out conditional rushing CRPS improves about 2.24%; the combined tail
Brier score improves about 2.96%. Other components are preserved unless their
own checks pass. The accepted model loads only for slate dates after October 26.
This is evidence about the per-carry conditional distribution, not calibrated
whole-game fantasy points, player ceilings, contest realism or portfolio ROI.

Accepted immutable versions and their index are committed with aggregate public
reports. The live shared NFL simulation loads the dated accepted version into
projection fitting, market fitting and both independent simulation samples.
Model identity participates in cache keys. Corrupt/incompatible optional models
fall back to an explicitly labeled baseline; old prepared outcomes cannot be
used after the active version changes. CSV point projections remain targets.

## Broader player and full-game validation

Stable-GSIS-ID/current-team profiles cover attempts, carries, targets, catches,
yards and TDs. A profile needs four team games before it can affect a live role.
Per-game opportunity concentration, pace and yardage environment are fitted
using frozen pregame cases. Another later full-game set checks every raw stat,
including QB/RB/WR/TE/K/DST, and joint variogram/energy scores in both DK and FD
contexts. Candidate replays rerun projection and market fitting. These broader
updates remain inactive until their own validation passes.

Pregame snapshots are private, retained in prepared manifests and the existing
diagnostic archive. They preserve pool, roles, fitter settings, weather,
markets, correlation and incumbent model identity. Started/undated games never
create supposedly pregame snapshots. A dated native salary field can establish
an activation date without inventing kickoff clocks.

The exact raw-stat importer pairs complete canonical FINAL rows with those
snapshots, rejects missing/ambiguous identities and values, and retains source
hashes. Older reduced PBP or contest FPTS cannot replace missing raw events.
Automatic acquisition of a complete raw-stat feed for this broader replay layer
remains unfinished, but it no longer prevents supported component learning.

Blocked-kick mechanisms, overtime, substitutions and exact special-team return
modeling remain limitations of the underlying engine.

```sh
python scripts/archive_nfl_learning_games.py
python -m simmah_nfl_event_learning
python scripts/learn_nfl_performance.py
python -m simmah_nfl_replay_inputs --snapshots /private/simulation_cache --actuals /private/final_raw_stats.csv --output /private/complete-cases
python scripts/learn_nfl_performance.py --fit-replays /private/earlier-complete-cases
python scripts/learn_nfl_performance.py --replays /private/later-complete-cases
```

Canonical raw rows require Game ID, timezone-aware Kickoff, Team, Opponent, Name,
FINAL Status, and every STAT_KEYS field, including explicit structural zeros.
Stable Player ID is preferred; a supplied ID mismatch never falls back to a name.
