# Defensive matchup backtest — October 18, 2026

The new defensive layer produced **no clear accuracy gain** on this completed
FanDuel full slate. The aggregate improvement was tiny, while players projected
for at least eight points became slightly less accurate. No parameters were
tuned after seeing these results.

| Metric | Without matchups | With matchups |
|---|---:|---:|
| Mean absolute player error | 3.5413 | 3.5380 |
| Distribution error (empirical CRPS, lower is better) | 2.40164 | 2.39714 |
| Actual results inside P10–P90 | 80.53% | 80.92% |
| MAE, projected 8+ points (78 players) | 5.6425 | 5.6565 |
| CRPS, projected 8+ points | 3.69528 | 3.70938 |

The paired CRPS change was -0.00450. A 10,000-resample bootstrap clustered by
NFL game gave a 95% interval of **-0.01475 to +0.00688**, including no improvement.
This interval covers game-sampling uncertainty for this slate; it is not a
multi-week validation. Independent streams both showed the small aggregate gain:
2.40142 to 2.39739 and 2.40206 to 2.39710.

## Design

- 271 saved positive-projection players; 262 matched actual player scores.
  Nine unmatched players were excluded from accuracy metrics rather than assigned
  assumed zeros. The JSON report lists them.
- 10,000 evaluation plus 10,000 independent construction outcomes per arm.
  Both arms used identical posted projections, seeds and reconstructed historical
  player roles. Neutral weather was used in both arms because a frozen pregame
  weather snapshot was unavailable.
- Historical weekly data was joined to schedule dates. Target-day, undated and
  future games were excluded; latest included game was October 15. Kickoffs were
  resolved from the October 18 schedule by matching the salary slate's team pairs.
- 242 players had matched pregame role histories. The new layer supplied matchup
  inputs for all 251 offensive players; DST outcomes change through shared games.
- Actual standings were first loaded only after fitting and simulating both arms.
  Player actuals were used for evaluation, never for fitting or matchup construction.
- Current copies of historical statistics were used. Publication-time snapshots
  are unavailable, so historical corrections cannot be ruled out. The input JSON
  freezes the exact reconstructed model inputs; source-file SHA-256 hashes are in
  the result JSON.

This is a paired player-outcome ablation on one slate, **not a test of portfolio
ROI, opponent construction, or a faithful replay of the original app run**.
It does not establish that the added layer improves expected contest returns.
Further testing should use additional untouched slates with frozen pregame inputs,
without tuning to this slate.

## Reproduce

Run `scripts/backtest_matchups.py` with the saved FD scoring inputs and contest
135326-281053768 standings, nflverse schedule CSV, and 2025/2026 weekly player
statistics. Arguments: `--players`, `--standings`, `--schedule`, `--history`,
`--cache-root`, `--output`; optional `--slate` defaults to `2026-10-18`.
No Streamlit runtime is needed. This script generates two full simulation bundles;
it does not lower simulation counts to speed up the test.

Sources:
https://github.com/nflverse/nfldata/blob/master/data/games.csv
https://github.com/nflverse/nflverse-data/releases/tag/stats_player
