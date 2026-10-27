# Joint opponent weights: offline experiment

`simmah_joint_field.py` fits probabilities over already legal, unique lineup
support. No production module imports it. It does not read player outcomes,
change scoring covariance, penalize selected lineups, or update the live field.

The current DK `expand_field` retains one copy of every unique sampled roster
and fills the rest uniformly. That is a bootstrap, not a calibrated popularity
model. The historical 321 versus 14 maximum-copy counts motivate investigation;
the new objective does not target either maximum count.

## Inputs and joint acceptance

- Supply canonical unique, legal support. `single_game_features` creates sparse
  special-role, FLEX, and optional overall pair indicators from six-player
  rosters. Eligibility, salaries, and team rules must already be checked by the
  platform-specific generator. Do not mix sports, platforms, slates, or formats.
- Supply feature targets in probabilities, with explicit tolerances. Future
  forecasts and pair-selection rules must be frozen before lock. Historical
  actual targets may be used for development only, not called predictive.
- Supply a positive prior and the exact **opponent** entry count for the compared
  population, excluding the user's entries. Capacity is not an entry count.
  Blank/unscorable entries require separate bookkeeping; never silently count
  them as legal rosters or omit them from the later payout calculation.
- Supply entry-weighted duplicate fractions in bands 1, 2–4, 5–9, 10–24, 25–99,
  and 100+. These sum to one. A lineup appearing three times contributes three
  entries to its band. Both observed and modeled curves must use the same N.

The loop minimizes squared, tolerance-scaled feature and duplication residuals,
with a KL penalty relative to the prior. Softmax weights preserve total mass.
It checks *every* supplied feature and duplication tolerance together and raises
`JointFitNotConverged` with diagnostics when they are not met. A failed fit does
not return weights as accepted or relax its targets. Immediate support-range
checks catch some missing-support cases; nonconvergence does not prove global
infeasibility of this nonlinear problem.

## Duplication calculation and sampling

For lineup probability p at field size N, a tagged entry's other copies follow
Binomial(N−1, p). The exact expected entry fraction in each count band is computed
analytically, with an analytic gradient. No Monte Carlo field is generated inside
optimization. This avoids fitting random sampling fluctuations on every step.

One seeded multinomial draw produces the final counts with exact total N.
Sampled ownership and duplicate bands are reported separately from expectations;
the draw is not rerolled until favorable. The maximum count is a reported outcome,
not a fitted target. The model assumes IID entries; it does not yet represent
an individual entrant's multi-lineup portfolio behavior.

The fitter can only reweight its supplied support. If the necessary popular
rosters or combinations are absent, broader proposals/support generation may
be required. More optimizer iterations cannot repair missing rosters. Large
support performance and hosted memory requirements have not been benchmarked.

## Validation performed and remaining work

Six tests passed: role/pair feature correctness and canonical deduplication;
expected duplication against independent Monte Carlo counts; analytic gradient
against finite differences; simultaneous fit of known synthetic targets;
seeded count reproducibility and input immutability; rejection of unmet
concentration targets, unsupported features, and field-count mismatches.

Run:

```bash
python -m unittest discover -s tests -p 'test_joint_field.py'
```

These are implementation checks, not improved real-contest calibration results.
Next: adapt the saved calibration packages and standings to the input contract;
report support coverage, baseline/fit residuals, and equal-N duplicate curves.
Train/select parameters only on development slates. Freeze before evaluating
later untouched slates. FD payout-ladder confirmation and platform CSV upload
acceptance remain independent checks. No claim of improved ROI is established.
