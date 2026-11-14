# Core regression and unknown absence records — offline diagnostic, 2026-11-14

**No forecast adjustment, new threshold tuning or promotion. Production and PR #77 are untouched.** The prior candidate's fresh-vacancy boost was zero in every chronological fold. Its changes came from recency weights and240-minute normalization, not demonstrated injury-vacancy redistribution. No usage-rate model changed in that experiment.

## The requested core slice does not show the assumed regression
Use the29-game development-verification set, primary latest pretip team snapshots, original audited cohort and provider-defined core>=28 as an evaluation stratum. Active means the archived Injury Status is exactly Active; it is not a medical certification. Provider tiers are never forecast features.

| Core cohort | Forecasts | Original MAE | Tiered MAE |
|---|---:|---:|---:|
| Snapshot-Active, injury-affected team |69|4.754|4.628|
| Snapshot-Active, no detected core vacancy |151|4.635|4.968|
| Other availability status |5|8.947|8.996|
| All core |225|4.767|4.953|

The injury-associated Active-core slice improves. The151 no-detected-vacancy observations add50.25 total absolute-error minutes, offset by−8.72 in the69 injury-associated observations; the other five add0.25. No detected vacancy does not prove full strength. These are descriptive results, not causal evidence about coach decisions or injuries.

## Positions and historical archetypes
Positions come from the latest strictly earlier saved boxscore on the same team, completed before snapshot capture. Only G/F/C labels are supported; finer PG/SG/wing archetypes are not invented.

| All snapshot-Active core players | Forecasts | Original MAE | Tiered MAE | Change |
|---|---:|---:|---:|---:|
| Guards |113|4.589|4.886|+0.298|
| Centers |29|4.496|4.619|+0.123|
| Forwards |78|4.859|4.914|+0.056|

Guards account for33.62 of41.53 net additional absolute-error minutes among all220 Active-core forecasts. Within injury-affected teams, guards are effectively flat4.445→4.457 (39 rows), centers improve5.459→5.214 (10), forwards improve5.005→4.666 (20). Therefore a broad injury-driven bench-boost explanation does not fit this slice.

A stronger diagnostic archetype is recent minute growth: baseline last5 historical raw mean exceeds the last10/half-life5 mean by>3 minutes. This is a fixed diagnostic bin, not a model gate optimized on outcomes. Among29 Active-core observations with that signal, MAE4.850→6.060;20 worsen,19 of those with downward forecast shifts. The other191 within3-minute observations are4.645→4.679. These groups overlap the position groups and should not have their contributions added.

Individual injury-slice regressions include Jeremiah Fears(NO, Nov13): forecast32.70→29.45, actual34; Brayden Burries(MIL, Nov10):27.32→22.19, actual26; Donovan Mitchell(CLE, Nov13):33.81→35.77, actual33. These are one-game examples, not stable player-specific effects. The final example worsens from an upward shift, showing why every error cannot be described as core minutes stolen by the bench.

## Mechanics ablation without retuning
Reconstruct all available-player raw weights and produce240-minute bounded counterfactuals. Core-only changes the long lookback on independent historical-core players while preserving baseline bench weights. Bench-only changes the fast bench lookback while preserving baseline core raw weights. Normalization remains shared, so final core minutes can change in either arm. Combined output reproduces the candidate within numerical tolerance. Effects are nonlinear and not additive or causal game-outcome effects.

| Cohort | Original | Core-lookback-only | Bench-lookback-only | Combined |
|---|---:|---:|---:|---:|
| All core225 |4.767|4.841|4.873|4.953|
| Recent-growth Active core29 |4.850|5.971|4.991|6.060|
| Active core on injury teams69 |4.754|4.719|4.637|4.628|

The recent-growth subgroup's error is mainly associated with the longer core lookback, consistent with lagging a changing role. This does not prove that this mechanism generalizes, or justify a newly tuned threshold on these same29 games. An adaptive role-change gate is a future hypothesis for new data, not a promoted fix. A vacancy-size gate alone is not supported as the explanation for the observed core regression.

## Audit of all14 unknown core-OUT observations
Inspect the26 prior-game observations marked unknown across those14 deduplicated player-game cases. Compare normalized names AND a strictly earlier known positive-minute athlete ID against all athletes in the saved source game, including other teams. Preserve complete flattened raw source athlete lists, fields and source hashes in the report.

**All26 unknown prior-game observations omit the athlete from the source boxscore entirely. Zero missed positive MIN records, zero missed explicit DNP flags and zero verified ID/name normalization gaps were found.** The loader `parse_game` retains the provided boxscore unchanged; it does not filter out supplied DNP athletes. A regression test confirms flag preservation.

Supporting archived pre-tip OUT snapshots exist for four of these prior-game observations (Chet Holmgren, Anthony Davis, Josh Hart, Tyrese Haliburton cases). Snapshot capture is checked before both the prior game's observed opening and the current forecast capture. These add historical pregame-unavailability evidence, but do not certify final non-participation or a three-DNP streak. No participation label was changed using them.

The audited records do not contain authoritative inactive lists or explicit DNP evidence for these omitted athletes. Resolving them requires a dated complete inactive roster, explicit historical DNP/gamebook evidence, or another independently verified participation source—not interpreting omission as zero. No new ongoing-absence case or medical reason is manufactured. No broader external injury-history backfill was completed or claimed in this diagnostic.

## Scope and validation
All29 games have already informed development; this is explanatory analysis, not a new untouched holdout. No candidate, exposure setting, selector, live projection or PR #77 code changed. Original58 tests remain green; five added tests cover omitted-record handling, source-positive/DNP evidence, same-team exact-ID gaps, cross-team and ambiguous identities, zero-minute ambiguity and archival DNP-field preservation.63 targeted tests pass. Tests establish checked invariants, not predictive accuracy or source completeness.
