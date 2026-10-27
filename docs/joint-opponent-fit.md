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

## October 26 DAL–PHI historical support preflight

Reproducible adapter: `scripts/preflight_joint_field.py`. Aggregate evidence:
`benchmarks/joint-field-preflight-dk.json` and
`benchmarks/joint-field-preflight-fd.json`. Source hashes match the previously
verified replay inputs. Relevant package members are independently hash-checked.
This is retrospective development data, not untouched validation.

| Duplicate copies per roster | DK entry fraction | FD entry fraction |
|---|---:|---:|
| 1 | 9.90% | 5.97% |
| 2–4 | 14.13% | 7.74% |
| 5–9 | 13.64% | 8.04% |
| 10–24 | 21.60% | 15.68% |
| 25–99 | 27.59% | 25.19% |
| 100+ | 13.15% | 37.37% |

All six bands are populated on both sites. Denominators are complete scored
opponents only: DK 47,051 entries / 9,188 distinct lineups, FD 138,505 / 16,435.
Own entries (20 DK / 60 FD) and unparsed or empty opponents (491 DK / 1,040 FD)
are separately reconciled to the full contest row counts. Parsed roster scores
reconcile to published player points, including the special-role multiplier.
FD finality remains unverified because its CSV has no TimeRemaining column.
These concentration diagnostics do not require or verify a payout ladder.

Each 5,000-candidate pool contains all 105 pairs among the 15 most-owned actual
players. The least-represented pair appears in nine DK candidates and 38 FD
candidates. Nevertheless, sparse LP feasibility checks on role ownership alone,
and on role ownership plus those pairs, both fail at ±0.005 probability
(0.5 percentage points per feature) on both platforms. Presence is not joint
feasibility. The original full-field check found the following absent FLEX support (classification corrected below):

- DK: Zach Ertz, 2.1551% observed, zero support.
- FD: Zach Ertz, 2.0519%, and Jaydon Blue, 1.2541%, both zero support.

The existing opponent supports have the same missing-role issue. DK has 10,000
unique opponent rosters; FD has 5,411. All their top-15 pairs also occur, but their
role/pair LP checks still fail. No nonlinear joint fit was attempted after these
necessary conditions failed.

A separate support-size bound follows from the duplicate bands: entry mass in
a band with at most b copies requires at least mass*N/b expected unique rosters.
Summing across bands, allowing 0.5 percentage points of error per band, gives
lower bounds of 7,255.11 DK and 12,464.79 FD expected unique rosters. A support
with 5,000 rows cannot meet those band tolerances regardless of weighting. At
least 7,256 DK / 12,465 FD support rows are necessary under that bound, not
sufficient. Exact empirical entry-count bands imply at least 7,591 / 13,446
unique rosters. Matching the exact empirical distinct count would require at
least 9,188 / 16,435, a stronger requirement than the band objective alone.

Candidate support passes captured salary/team checks. Actual salary validation
is incomplete: some opponent players are absent from the captured build pool
(1,474 DK / 5,982 FD entries affected). Known-salary entries also include 884 DK
and 708 FD below the captured own-build salary minimum. These complete scored
rosters remain in concentration targets; they are not silently discarded to
make support appear feasible. Full-field modeling must distinguish declared inactive-player rosters from the
playable-player population. Do not add inactive players to the user's build
pool to satisfy historical full-field ownership. More opponent support may still
be needed for concentration targets. This does not require expanding the user's
5,000-lineup portfolio candidate build.


### Correction: Ertz inactive for this game

The user clarified that Zach Ertz was not activated. The audit now accepts explicit
`--inactive-player` declarations, records their provenance as user-reported, and
keeps those rosters in full-field concentration counts. Zero published points
alone do not establish inactivity. Ertz's published FPTS is 0.0 on both sites.
No build pool, scoring covariance, or live opponent generator was modified.

There are 1,069 DK opponent entries across 419 unique rosters containing Ertz,
and 2,876 FD entries across 770 unique rosters. This includes both special and
FLEX roles, so it is larger than the earlier FLEX-only counts. These entries must
remain in ranks and payout calculations; they are not missing playable-player
coverage to solve by activating Ertz. Their full scores still include the other
five players' points.

A second feasibility check conditions only on **Ertz-free** opponents (not a
claim that every remaining player was active). At the same 0.5-percentage-point
feature tolerance, DK role-only and role-plus-pair targets are now feasible on
both the 5,000-candidate pool and the 10,000-roster opponent support. The original
full-field rejection therefore must not be described as a proven DK active-player
pair-coverage failure. FD remains infeasible after this correction; other missing
player support needs status review before any recommendation to broaden eligibility.
The full-field duplicate bands and bounds are unchanged; conditional duplication
targets have not been fitted. Full-field calibration needs separate accounting
for inactive-player rosters rather than silently removing them from the contest.

Reproduce by adding `--inactive-player 'Zach Ertz'` to the preflight command.
The JSON reports retain both full-field and conditional checks with denominators.


### FD remaining gap: Jaydon Blue sensitivity check

The FD original entry-template salary reference lists Jaydon Blue as RB, with
blank injury fields. He is absent from the captured build and opponent pools;
published FPTS is 0.0. Neither a blank injury field nor zero points establishes
activation status. The user's inactivity clarification applies to Ertz, not Blue.

A hypothetical exclusion check removes both players' rosters **only from the
conditional target population**, retaining all full-field accounting. There are
4,586 such opponents, leaving 133,919 complete scored opponents. At ±0.5 percentage
points, role-only and role-plus-the-same-105-pair targets are feasible on both the
5,000-candidate pool and 5,411-roster opponent support. Thus Blue's unsupported
role is sufficient to explain the remaining necessary-condition failure after
the Ertz correction; there is no evidence here requiring scoring covariance or
stack-rule changes. This does not establish nonlinear duplication convergence.

No eligibility was changed. Blue's game availability needs confirmation before
classifying his entries as inactive-player lineups or playable missing support.
Aggregate sensitivity evidence is in
`benchmarks/fd-support-blue-sensitivity.json`. The full-field FD payout ladder
and platform upload acceptance remain unverified.


### Blue availability resolved from official chronology

The prior activation-unverified status is superseded by official transaction
evidence: Blue was signed to the active roster October 17, waived October 20,
and signed to the practice squad October 22. The October 26 team elevations
name Elijah Mitchell and Keyshawn James-Newby, not Blue. Blue is absent from
the official gamebook roster/participation lists. Together these support the
assessment that Blue was a practice-squad player not elevated for DAL–PHI.
This conclusion is not based on his zero fantasy points or absence from the
standard inactive list, which alone would not establish game eligibility.

Sources and exact URLs: `benchmarks/blue-availability-2026-10-26.json`. Blue
rosters can therefore be categorized separately from playable-player support
for this historical development audit, with their full scores retained in
full-field ranks and ties. This changes the status evidence, not live eligibility
or opponent generation. Nonlinear duplicate-band convergence remains untested.

Live platform entry review was attempted in the available browser. DraftKings
and FanDuel both returned Site Unavailable, including one reload each. No
account entry screens were accessible and no live CSV upload or slot mapping
was verified. Earlier 20-DK/60-FD historical roster reproduction and offline
structural export checks remain separate evidence.

Official sources:
- https://www.philadelphiaeagles.com/team/transactions/
- https://www.nflgsis.com/2026/REG/07/60284/Gamebook.pdf


## Executed DK duplicate-band trial

`run_joint_field_trial.py` executed both captured supports with the same seed
83, 500-iteration limit, and 0.005 probability tolerance for every feature and
duplication band. The candidate prior is uniform; the opponent-support prior
is proportional to its saved entry counts. No target or tolerance was relaxed.
Both runs were rejected after reaching the iteration limit.

The population is 45,932 complete scored opponents containing neither Ertz nor
Blue. Their 1,119 inactive-player opponent entries are retained as a separate
historical stratum, alongside 491 incomplete/unparsed opponents and 20 user
entries: 45,932 + 1,119 + 491 + 20 = 47,562. Matching the conditional histogram
at 47,562 would mix populations. The background counts reconcile, but this
trial does not recompute payouts or establish a prospective inactive-entry model.

| Support | Max feature error | Max duplicate-band error | Duration | Accepted |
|---|---:|---:|---:|---|
| 5,000 candidate rosters | 2.47 pp | 8.23 pp | 8.73 s | No |
| 10,000 opponent rosters | 3.12 pp | 3.18 pp | 15.40 s | No |

The simultaneous soft objective trades off feature and band residuals. Its
nonconvergence is not a claim that role/pair targets alone are infeasible.
Expected entry fractions at the final iterates:

| Copies | Actual | 5,000 support | 10,000 support |
|---|---:|---:|---:|
| 1 | 9.50% | 1.27% | 6.32% |
| 2–4 | 13.82% | 14.14% | 14.31% |
| 5–9 | 13.47% | 14.86% | 13.84% |
| 10–24 | 21.62% | 23.57% | 22.27% |
| 25–99 | 28.13% | 30.39% | 28.92% |
| 100+ | 13.47% | 15.77% | 14.34% |

A necessary IID singleton bound independently certifies that neither support
size can meet the singleton target within tolerance. For any roster probability
p, its expected singleton entry fraction is p*(1-p)^(N-1), maximized at p=1/N.
Summing this bound over J support rosters gives at most
J*(1/N)*(1-1/N)^(N-1). At this N the upper bounds are 4.00% for J=5,000 and
8.01% for J=10,000, while the observed target is 9.50% (minimum accepted 9.00%).
At least 11,233 unique support rosters are necessary under this bound, not
sufficient for a simultaneous fit. This is a restriction of the current IID
expected-count model; it is not proof of missing chalk pairs or infeasibility
for every possible field generator. More iterations cannot defeat this bound.

The next development step is broader **opponent** support or an explicitly
justified alternative entry-count model. The user's 5,000 lineup build is not
being expanded or changed by this audit. No accepted field, production change,
improved ROI result, or untouched-slate validation was produced. Evidence:
`benchmarks/joint-field-trial-dk.json`.

Reproduce:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/run_joint_field_trial.py \
  --package /path/to/DK_Calibration_Solver.zip \
  --standings /path/to/contest-standings-197055079.zip \
  --exclude-player 'Zach Ertz' --exclude-player 'Jaydon Blue' \
  --output /path/to/joint-field-trial-dk.json
```

Existing joint-model tests: six passed again after the trial. Source hashes
and the full-field stratum totals reconcile; each expected duplicate curve sums
to one. The JSON report is written atomically after each support completes.
