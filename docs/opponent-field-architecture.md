# Opponent-field architecture

Candidate lineup generation and opponent-field generation are separate models.

## Candidate builder

Use the fast bounded weighted builder to efficiently search legal lineups for the user's portfolio. Candidate weights may use simulated ceiling, mean, volatility, ownership/leverage, locks/fades, exposure controls, salary rules, and user-selected stacks.

## Opponent field

Do not reuse the user's candidate-builder rules as the opponent model. Build a persistent population of complete legal opponent lineups before contest scoring.

The opponent model should be calibrated by contest profile and actual historical fields. Inputs/features should include, when available:

- contest format and site
- field size
- entry fee / stakes / max-entry structure
- player ownership
- Captain/MVP ownership for single-game contests
- salary usage distribution
- full-roster QB stack and bring-back frequencies
- common roster constructions
- exact-lineup duplicate frequencies

The opponent field should preserve repeated exact lineups rather than forcing uniqueness. Those multiplicities feed tie splitting and expected payout/ROI.

## Contest simulation

1. Generate/calibrate the complete opponent population.
2. Generate the user's candidate population separately.
3. Score both populations across the same simulated game/slate outcomes.
4. Rank complete lineups per scenario.
5. Split payouts across exact ties/duplicate copies.
6. Aggregate Win%, Top 1%, Top 5%, Top 10%, Cash%, expected prize, expected net, and expected ROI.

## PBP compatibility

The planned NFL PBP engine changes the source of player fantasy outcomes, not the field-building architecture:

Historical football data + current projections/injuries -> PBP outcomes -> score candidate and opponent lineups -> contest/ROI simulation.

## Calibration

After lock, compare the projected field against actual contest entries. Track at minimum:

- marginal player ownership error
- Captain/MVP ownership error
- salary-spend distribution
- stack/construction frequencies
- exact-lineup duplicate-count distribution
- lineup strength distribution

Use completed contests as calibration/holdout data rather than silently feeding the user's selected portfolio back into the opponent model.
