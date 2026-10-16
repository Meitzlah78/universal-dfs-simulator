# Projected Dupes calibration

## SEA/DEN completed-contest benchmark

Use the completed 47,562-entry DraftKings Showdown field as a holdout benchmark for future duplicate estimation.

The current summed lineup ownership score is not a sufficient duplicate estimator. In the 20-lineup backtest it had only moderate linear association with exact field copies and weak rank association; observed exact copies ranged from 0 to 80.

## Target

Add a dedicated `Projected Dupes` estimate for DraftKings Showdown and keep `Lineup Ownership Score (%)` as a separate descriptive metric.

The estimator should be driven by lineup-level construction features rather than summed ownership alone. At minimum include:

- captain ownership / captain identity
- FLEX ownerships and their interaction/product signal
- salary used and salary remaining
- number of highly owned players
- duplicated chalk combinations / teammate stacks
- roster construction and team split
- QB count, DST count and kicker count when applicable
- contest field size

Do not use completed-contest exact duplicate counts in live prediction. They are calibration/validation labels only.

## Selection behavior

Projected dupes should feed payout/ROI split logic and can be used as a portfolio leverage/tiebreak feature, but must not become a hard hidden diversification constraint. Existing explicit Portfolio and Min Uniques controls remain authoritative.

## Validation

For a completed contest, canonicalize a Showdown lineup as `(captain, sorted FLEX players)` so FLEX order never changes the duplicate count. Compare predicted versus actual copies using MAE plus Pearson and Spearman association. Report calibration by projected-dupe bucket and specifically track unique/near-unique (0-2 copies) and heavily duplicated (20+ copies) lineups.

SEA/DEN observed copies for the latest 20-lineup portfolio included two unique constructions and a maximum of 80 copies, providing useful coverage across the target range.
