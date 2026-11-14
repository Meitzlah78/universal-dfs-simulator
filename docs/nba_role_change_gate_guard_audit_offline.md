# Role-change gate and guard audit — offline, 2026-11-14

**The gate partially improves the independent minutes forecast, but does not beat provider point estimates or justify promotion.** Production and PR #77 are untouched. No injury boost, absence label, variance model, fantasy projection or portfolio setting changed.

## Experiment
Use the same240-minute independent forecast and recovered available rosters:144 team/site snapshots,2134 candidate forecasts, including259 candidates without explicit actual-minute records. Those259 remain unscored. Original baseline reconstruction differs only by numerical precision. The29 verification games have already informed development; chronological separation is maintained, but this is not a pristine final holdout.

Independent tiers come from the original raw history mean (core>=28, bench<18, rotation otherwise). The prior tiered candidate used core last10/half-life5, rotation last5/half-life3, bench last3/half-life1. The gate detects raw last5/half-life3 mean minus raw last10/half-life5 mean above a threshold, only for historical-core players. It substitutes either the original last5 estimate or the fast last3 estimate for those rising cores, retaining the other tier rules. Normalize all available players to240 with a48-minute cap. Provider minutes, positions, rest and expected-starter flags are not predictive gate features.

Predefine thresholds2,3,4 minutes and two fallback windows before this run. Each test date selects solely by earlier-date deduplicated physical-game-average MAE, on all matched available players including provider-zero rows. October30/eight games initialize training; five later dates provide29 evaluation games and629 primary audited player forecasts. Both sites of a game stay on the same side of the cutoff. No per-slate tuning on the test date.

The gate-only selector chooses threshold2 with the original last5 fallback in all five folds. A separate conservative family selector can retain the original baseline: it does so for the first three dates, then selects the2-minute gate for Nov11/13. Fixed3-minute results are a predeclared sensitivity, not selected afterward as the winner.

## Chronological point-forecast results
MAE in minutes, lower is better:

| Cohort | Provider | Original | Ungated tiered | Fixed3 gate | Earlier-selected gate |
|---|---:|---:|---:|---:|---:|
| All629 audited forecasts |5.121|5.490|5.376|5.326|5.340|
| Core225 |4.324|4.767|4.953|4.837|4.853|
| Rotation210 |4.943|5.261|5.267|5.230|5.242|
| Bench194 |6.237|6.577|5.986|5.998|6.011|
| Injury-associated205 |4.737|5.692|5.432|5.435|5.459|

The gate recovers some core regression while retaining most bench improvement, but core remains worse than the original baseline and injury-slice performance does not improve further. Overall >5-minute miss rate: original48.2%, ungated44.7%, selected gate44.8%, provider37.0%. The conservative family selector has overallMAE5.359/core4.730/bench6.226; it is not evidence of an independent-model win over the provider or production readiness.

Conditional game-cluster bootstrap, selected gate minus original:−0.149 minutes,95% interval−0.301 to−0.0065. Versus ungated tiered:−0.0358, interval−0.0934 to+0.0182. Versus provider:+0.201, interval−0.180 to+0.582. These intervals condition on fitted choices and omit training uncertainty/multiple comparisons. The development improvement is worth recording; it does not certify production gains. No independent fantasy-point benchmark is unlocked.

##113 snapshot-Active guard-core forecasts
Guard positions come from strictly earlier boxscores. Snapshot Active is not medical confirmation. Provider-core tier is a diagnostic cohort definition only. Saved expected-starter flags were recovered from the earlier ownership/role evidence and matched by package/player ID with exact capture-timestamp parity. They are diagnostic provider expectations, not confirmed current starting lineups, and never enter threshold training or predictions.

| Guard cohort | Forecasts | Original MAE | Ungated tiered | Selected gate |
|---|---:|---:|---:|---:|
| All113 |113|4.589|4.886|4.709|
| Not back-to-back |92|4.511|4.917|4.643|
| Back-to-back |21|4.931|4.752|4.998|
| Stable expected starter |98|4.414|4.787|4.547|
| Expected promotion from prior bench role |4|8.620|8.600|8.849|
| Stable expected bench role |7|4.871|4.551|4.764|
| Prior starter role unknown |4|4.343|4.195|4.432|

Rest is derived from the earlier completed team-game calendar, including OT. Current expected starter is compared with the previous game's recorded starter flag only if prior participation is verified. Missing rows are not classified as bench or as lineup changes.

The ungated regression occurs primarily on non-back-to-back games and among stable expected starters. Back-to-backs have higher absolute error but do not explain the increase caused by the longer lookback in this sample. Four promotion cases are difficult but too few to establish a reliable mechanism; their near-zero ungated change cannot explain the broad guard regression. A player can have a growing minutes role while remaining a starter, so starter-change flags alone are not a sufficient role-change detector. These are small overlapping diagnostic slices, not causal effects or reasons to fit a new rest-specific rule on the same games.

## Omission handling and mechanics
No unknown athlete omission is converted to DNP, non-starter or zero-minute history. Existing independent windows use explicit earlier observations; skipping an unknown record preserves the last known history rather than resetting it, but does not establish that an older role remains current. This experiment does not repair the14 unknown absence observations or prove their streak lengths. The259 missing actuals remain excluded from scoring without excluding them from team allocation.

All144 team rotations remain bounded and sum to240; maximum numerical budget error1.2e-13 minutes.71 targeted tests pass, retaining all63 prior checks plus gate thresholds, fallback modes, input immutability/validation, insufficient-support rejection and conservative starter-transition labels. Test success validates checked mechanics, not predictive/source completeness. No deployment or PR #77 edits.
