# NFL performance learning

The weekly archive now records immutable **candidates**, not automatic claims of
improvement. The first local run used 29 training games (weeks 5–6) and 14 later
week-7 diagnostic games. No candidate is active.

## Scope

- Stable-ID player profiles: attempts, carries, targets, completions, receptions,
  yards, touchdowns and interceptions. Current-team matching prevents a trade
  from joining a player to the wrong historical team. A player needs four team
  games before a fitted profile can affect a live role.
- Event efficiency: passing, rushing, receiving, sacks, turnovers, conversions,
  PATs and distance-conditioned FG accuracy. Each event uses its own denominator.
- Spread: rushing-yard standard deviation, receiving gamma shape and per-game
  target/carry opportunity concentration.
- Shared outcomes: pace and yardage environment. Frozen full-engine fitting
  evaluates volume dispersion and dependence together; final validation uses
  another later set of games. Pairwise variogram and multivariate energy scores
  assess cross-player dependence, including offensive/DST links.
- Every raw stat in the existing engine's `STAT_KEYS`, including K and DST, is
  checked at promotion. Unsupported mechanisms (notably blocked kicks), OT,
  injury substitutions and exact special-teams return modeling remain engine
  limitations; the learner does not implement those missing football events.

## Activation requirements

1. Dated, nonoverlapping game/play archive rows with regulation-end markers.
   An end marker is a completeness check, not independent official verification.
2. Train on earlier complete games; event selection uses a later whole-game
   date block. Never split plays from one game between train/test.
3. Optional joint fitting uses still-later frozen pregame cases. Those games
   become selection data and cannot also be promotion games.
4. At least 20 distinct **additional** games with both DK and FD contexts,
   pregame timestamps, full frozen pool/roles/fitter/weather/market inputs, and
   explicit final raw stat lines for every included player. Missing values are
   errors, never presumed zeros. QB/RB/WR/TE/K/DST must all be represented.
5. No position/stat loss may worsen for mean error, CRPS or variance-sensitive
   likelihood. Joint variogram loss must improve at least 0.5%, and energy score
   must not worsen. Synthetic fixtures test these gates, not predictive accuracy.
6. Write the accepted immutable version before atomically updating the index.
   Existing accepted versions remain available. New versions require matching
   incumbent snapshots. Models load only for slate dates after validation ends;
   changed engine code requires revalidation. Model identity participates in
   fitter/outcome cache identity and BUILD checks for changed active versions.

Candidate replays rerun projection and market fitting with the proposed event
parameters; frozen baseline fitter parameters are not reused for changed candidates.

External CSV projections remain the scoring targets. Learned values affect the
shared play generator, projection pilot, market pilot and independent outcome
samples consistently. No fantasy-point multipliers or ROI fitting are added.

## Saved inputs and missing data

When SIM runs before confirmed tipoff, per-game pregame snapshots are retained
under the private simulation cache and embedded in prepared manifests for the
existing diagnostic-package archive. Missing/conflicting clocks or games already
started do not create supposedly pregame snapshots. These files are private;
workflow commits contain public NFL archives and aggregate model reports only.

Older reduced archives omit kick results, fumble-loss and some defensive fields.
The weekly downloader now retains those columns when supplied. Existing files
are not backfilled with invented values. Exact completed-contest fantasy scores
alone cannot identify underlying volume, efficiency and covariance errors;
they do not satisfy the raw-stat promotion gate. The CLI requires complete replay
cases; automatic raw-actual assembly from older saved contests is not implemented.

## Commands

```sh
python scripts/learn_nfl_performance.py
python scripts/learn_nfl_performance.py --fit-replays /private/earlier-complete-cases
python scripts/learn_nfl_performance.py --replays /private/later-complete-cases
python -m unittest discover -s tests -p test_nfl_learning.py -v
```

A replay case has `game_id`, timezone-aware `kickoff` and `frozen_at`, `platform`,
`pool` records, `roles`, `projection_inputs`, `weather`, `market_gain`,
`fit_settings` (pilot_n and iterations), `market_targets`, and
`actual_stats` keyed by exact frozen player name. Every actual line must contain
all `STAT_KEYS`. Captures include `incumbent_version` and `incumbent_parameters`.
No name-based fuzzy merge or automatic zero fill is allowed.

This is a first implementation of the training/validation connection. It is not
proof of better player forecasts, realistic contest opponents or higher ROI.
