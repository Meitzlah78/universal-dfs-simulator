# Eoin Moore Kaggle source audit — 2026-10-20

Downloaded the public `Games.csv`, `PlayerStatistics.csv` and `TeamStatistics.csv`
from the dataset's Kaggle per-file download endpoints. `audit.json` records exact
byte sizes and SHA-256 hashes. Raw files are not committed. The source listing
reported file creation on 2026-10-19; no Kaggle version number was independently
captured, so hashes identify this download rather than an assumed version.

Run `python scripts/nba_kaggle_audit.py --folder DOWNLOAD_FOLDER --output audit.json`.
The fixed window is 2023-01-01 inclusive through 2026-10-20 exclusive; preseason
and All-Star games are excluded. Cup and play-in records are reported explicitly.

## Findings

- 4,731 games, 124,905 player rows, 884 players; no duplicate game/player rows.
- 9,454 matched player/team point ledgers; 10 team rows have no matching player
  ledger. This is internal reconciliation, not independent final-game proof.
- 23,388 explicit DNP/DND/NWT nonparticipation rows with no contradictory minutes
  or statistical production. Their blank minutes can be represented as zero;
  202 remaining missing-minute rows remain unresolved.
- Only 169 of 9,464 team rows pass the strict minute-ledger check within one
  minute and have no unresolved players. Minutes display mixed historical
  precision: all observed 2023 minutes are integers, while most 2025/2026 rows
  contain fractional values. Shortfalls remain common; do not force them to 240
  or assume one uniform format without source investigation.
- 646 zero-minute rows lack explicit nonparticipation comments; these are flagged
  rather than assigned a fabricated DNP reason.
- Team-minute budgets suggest 462 overtime team rows and two other durations.
  These are audit observations, not certified overtime counts for training.

Useful candidate source for player statistics and broad historical outcomes.
Not approved as an exact-minutes training corpus yet. No historical frozen
provider forecasts or DFS-to-NBA ID mapping are supplied by these files; they
cannot by themselves establish a prospective minutes-model backtest.

No live projections, simulation parameters or models were updated. Raw download
access succeeded without a Kaggle credential in this run. Future availability
and source revisions must be checked; rerun and compare hashes before reuse.
