# Historical team-minutes baseline pilot

Collected all final games on 21 consecutive dates, January 1–21, 2025, from
ESPN's scoreboard and summary feeds. 151/153 games passed complete rotation,
team-budget and rounded box-score consistency checks. Source event IDs and raw
response hashes are in `source-audit.json`. This is a retrospective pilot of a
simple historical baseline, not validation of the live provider-anchored model.

## Method fixed before scoring

- Evaluation starts January 8. Require at least three earlier accepted team
  games, use up to the latest five. No same-date outcomes update forecasts.
- The deterministic forecast is the mean of those historical team allocations.
  The distribution consists of those same complete allocations. Both therefore
  have the same point forecast; changing the distribution alone is not claimed
  to improve mean accuracy.
- Each historical allocation has 240 regulation minutes. Actual overtime is
  isolated using period-specific stints, not proportional box-score scaling.
- Forecast player IDs come from earlier team history. The current box roster is
  used only for matching outcomes, not for selecting pregame rotations. New
  players, missing current players, insufficient history and unresolved actual
  statuses are counted separately. Missing current records are never made DNPs.
- Evaluate nominal central 80% interval coverage, MAE, empirical CRPS and Brier
  score for a fixed 30+ regulation-minute event. A fixed point forecast is a
  point mass when scoring probabilistic metrics. Lower CRPS/Brier is better.

## Results

2,528 matched player-games across 197 evaluated team-games:

| Measure | Result |
|---|---:|
| Minutes MAE | 5.87 |
| MAE among players who appeared | 5.77 |
| MAE among verified DNPs | 6.37 |
| Nominal 80% interval coverage | 56.4% |
| Average interval width | 10.50 minutes |
| Empirical distribution CRPS | 4.40 |
| Point forecast CRPS | 5.87 |
| Empirical Brier, 30+ minutes | 0.111 |
| Point forecast Brier, 30+ minutes | 0.164 |

Coverage issues: 400 prior-history players absent from the current box roster;
58 current players absent from prior team history; one team-game lacked enough
accepted history. There were 429 matched verified DNP rows. These exclusions
limit the interpretation of the matched-player error metrics.

The historical empirical distribution scores better than a point mass on these
probability metrics, but its 80% intervals capture only 56.4% of outcomes. It is
substantially under-dispersed and is not ready for promotion. No parameters were
tuned to these outcomes. No archived RotoWire minutes, injuries, trade/availability
or confirmed-lineup inputs are supplied, so this cannot establish improvement
over the live provider forecast or estimate lineup ROI.

## Reproduction and files

Run `python scripts/nba_minutes_pilot.py --cache CACHE_DIR --output-dir OUTPUT`.
The script downloads source summaries, rejects failed reconstructions and writes
actuals, forecasts, coverage issues and aggregate results. Caches can be reused.

The two `.csv.gz` files preserve the accepted actuals and matched forecasts.
`derived-file-manifest.json` records compressed and uncompressed hashes. IDs are
ESPN IDs; do not join to NBA or DK/FD IDs without an explicit crosswalk.
Only 21 January dates are evaluated; results should not be generalized to all
seasons or tonight's slate. No live lineup or simulation engine was changed.

Separately, the pregame archive now recognizes the real `Game Start` roster
column and treats naive provider clocks as Eastern, like late swap. This fixes
future capture; it does not reconstruct snapshots that were previously missed.
