# Blowout weighting on the frozen role-change gate — offline, 2026-11-14

**Decision: keep no historical blowout discount.** Earlier-date selection chooses the unchanged control in every fold. No role/starter definition, gate trigger, injury rule, absence label or production setting changes. PR #77 remains untouched.

## Available historical margins
The saved archive contains event-level home/away scores, not only final results. All219 games in the independent-minute history input have final margins, end-of-quarter margins for all four quarters, and usable fourth-quarter score trajectories. There are no missing Q4 profiles in this input. Derive a time-weighted mean absolute margin over the final six regulation minutes, using post-event score states held until the next game-clock event. This is not an event-count average. Preserve signed home-minus-away quarter-end margins and the number of last-six-minute seconds with absolute margin>=20 for audit.

At20 points,57/219 history games qualify by final margin versus53/219 by last-six-minute mean margin. At25 points,30 versus28. These are margin proxies, not verified player-specific garbage-time or coaching-pull labels. OT games were already excluded from the trailing-minute history; this experiment does not introduce an OT cap or alter that policy.

## Isolated, predeclared seven-arm grid
Retain the existing2-minute rise gate with last5/half-life3 fallback. Freeze historical tier membership and gate activation from the unchanged unweighted historical means. Core default remains last10/half-life5, rotation last5/half-life3 and bench last3/half-life1. Discounting changes only the weights applied to the already-selected historical observations, not who is a core player or who triggers the gate.

Compare no-discount control with three rules under EACH separate historical margin measure:

| Rule | Historical positive-minute observation weight |
|---|---|
| Hard20 |0.5 when margin>=20; otherwise1 |
| Hard25 |0.5 when margin>=25; otherwise1 |
| Linear |1 at/below10, linearly declining to0.25 at30, floor0.25 thereafter |

Recency weights multiply these discounts and are then normalized within the fixed observation window. No observation is deleted and no older game is pulled in to replace a discounted game. Recorded zero-minute observations retain their original full recency weight; they are not reclassified as blowout noise or new DNPs. Cold-start league priors stay unchanged. Unknown profile coverage defaults to neutral weight1 and is logged, never margin0. Historical observation AND margin profile must precede the forecast date/capture. Target-game scores cannot enter features.

Each complete independent team vector is allocated to240 minutes with0–48 bounds. Control reproduces the existing gate within7.2e-15 minutes. All2134 available candidates remain in their144 team/site snapshots;259 unknown actual-minute records remain unscored.

## Chronological selection and results
Initial October30/eight games train the first fold; five later dates provide29 development-verification games,629 primary audited forecasts. Each date chooses using only earlier-date physical-game-average MAE on all common available rows, including provider-zero rows. Ties prefer no discount. Evaluate final-margin and Q4 families separately, plus their combined family. All three selectors choose no discount in EVERY fold. The starter definition is intentionally unchanged; no multi-game starter model is tested here.

Point-forecast MAE in minutes:

| Arm | Overall629 | Core225 | Rotation210 | Bench194 |
|---|---:|---:|---:|---:|
|Provider|5.121|4.324|4.943|6.237|
|No discount/current gate|5.340|4.853|5.242|6.011|
|Final hard20|5.332|4.863|5.273|5.941|
|Final hard25|5.323|4.831|5.272|5.948|
|Final linear|5.377|4.889|5.376|5.945|
|Q4 hard20|5.326|4.845|5.268|5.945|
|Q4 hard25|5.326|4.829|5.275|5.958|
|Q4 linear|5.382|4.881|5.385|5.960|
|Earlier-date-selected combined|5.340|4.853|5.242|6.011|

Fixed-rule rows are development sensitivities, not test-set winners to promote afterward. The closest fixed core estimates are still approximately4.83, above the original independent4.77 target. Tiny fixed-rule overall gains do not demonstrate a reliable method selected before prediction. Selected schemes are identical to control, so selected-versus-control differences and conditional bootstrap intervals are exactly zero.

Stable expected-starter core rows (current one-game comparison, n200): selected control4.827MAE. Rising core diagnostic rows (provider-core and earlier last5-minus-last10>3, n30 including non-Active status):4.861. These are overlapping diagnostics, not a new multi-game definition; the earlier Active-only rising-core slice had29 rows. No new starter label was introduced halfway through this experiment.

The table is generated from summary.json; row CSVs retain full precision. No held-out result is used to switch to the best fixed rule.

## Interpretation and governance
This test does not causally quantify what fraction of4.85 core MAE comes from garbage time. It checks whether discounting large-margin historical observations improves a frozen forecast. Some large-margin minutes may still be informative about future game-script variation; they are not automatically bad data. The tested selection procedure does not support changing the current no-discount policy.

All29 dates have already informed development. Chronological rules prevent same-game leakage but do not make this a pristine final holdout. No fantasy interval, co-spike, scoring or contest-return gains are claimed. No unknown boxscore omission becomes zero/DNP, and source history gaps remain unresolved.

79 targeted tests pass, retaining the prior71. Added checks cover clock-time integration, nonmonotonic Q4 rejection, separate final/Q4 discounts, observation/profile cutoffs, full zero-minute weights, unknown-margin neutrality, fixed windows/cold starts and invalid inputs. Tests establish checked mechanics, not predictive readiness. Production and PR #77 are unchanged; multi-game starter definitions remain a separate next experiment.
