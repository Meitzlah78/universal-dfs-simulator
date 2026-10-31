# Broader ESPN rotation coverage — 2026-10-20

Tested all completed games on January 15, March 15, April 25 and June 1 in each
calendar year 2023–2026. The 16 dates yielded 81 games; some June dates had none.
This is a purposive multi-season sample, not an all-season completeness estimate.

## Results

| Calendar year | Parsed games | Accepted |
|---|---:|---:|
| 2023 | 19 | 17 |
| 2024 | 20 | 20 |
| 2025 | 22 | 21 |
| 2026 | 20 | 20 |
| Total | 81 | 78 |

Accepted games cover all 30 teams and include two overtime games. Checks require:
final status; event score matching final team scores; unique event IDs; complete
periods; reconstructable five-player stints; correct 240+25-per-OT team budgets;
and each participating player's minutes within 1.01 minutes of the displayed box
score (to allow whole-minute display rounding). Maximum accepted deviation was
0.55 minutes. These are same-source consistency checks, not independent proof
that each substitution timestamp is exact.

Rejected: 401469195 and 401705535 have invalid substitution sequences;
401468805 balances its team budget but differs from a player's box minutes by
1.985 minutes. Rejections are not repaired with guessed substitutions.

`audit.json` records every game, issues, source hashes, teams and budgets.
`accepted-player-minutes.csv` contains only accepted games, with separate
regulation and full-game values derived from stints, plus verified DNP status.
Unresolved zero rows remain labeled explicitly; they are not fabricated DNPs.
All IDs are ESPN IDs. An explicit crosswalk is required before joining NBA or
DFS IDs; names are labels only. These are actuals, not pregame inputs.

Reproduce with `python scripts/nba_rotation_coverage.py --cache CACHE_DIR
--output REPORT.json`. The exporter creates accepted actual rows from cached
summaries. Raw summaries are fetched from ESPN scoreboard/summary endpoints;
the audit records their SHA-256 hashes. No raw source payloads are committed.

This provides a much broader candidate source of precise actual minutes than
the previous one-game probe. Historical frozen pregame forecasts and injury
information are still required for a predictive uncertainty backtest. No live
projections, rotation models or simulation parameters were changed.
