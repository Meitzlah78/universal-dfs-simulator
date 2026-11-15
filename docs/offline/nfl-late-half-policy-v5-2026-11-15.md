# UNVALIDATED RESEARCH — NOT READY TO MERGE TO MAIN

Policy `late-half-management-v5`. Keep main and production unchanged, 2025 locked, both candidates frozen, and all V4 Q4/urgency behavior unchanged. This is repeatedly inspected 2024 development evidence, not an independent holdout.

## Audit before intervention

The passive V4 replay retained exact offensive timeout event states across all 285 labels / 291,840 trials. All 570 saved output dictionaries match exactly. It recorded 572,812 calls (1.9627604/game): 0.54335/game above 50 actual call seconds; 0.33808/game spending the final timeout with next down 1 or 2; 0.98713/game outside existing FG range. There were 12,373 calls with no positive outgoing runoff saving. These groups overlap and are not additive causal estimates.

The original 70-second threshold was pre-snap; actual calls were at 1–65 seconds under the driver's fixed five-live-second convention. The audit source is retained at research commit `3de757ed424a240148df75fbb04f27a3fd5576a1` with exact trace source hashes. Those are synthetic driver timestamps, not observed NFL PBP timeout timestamps.

## Frozen V5 rule

Preserve V4's final-120-second Q2 urgency, beyond-own-35 territory gate, lead below +21 and 20-second total interval cap. Change only the offensive timeout budget/clock rule:

- Actual call clock must be positive and <=50 seconds. With fixed five live seconds this means pre-snap half time <=55 and >5 seconds. Field and next down are post-play states.
- If more than one offensive timeout remains, allow the eligible stoppage.
- Reserve the final timeout unless next down is 3 or 4, or the offense is within existing FG range (distance <=40) with <=15 seconds left at the call.
- Do not call when the sampled/hurry interval is <=5 total seconds; there is no positive runoff to save under the existing live-time convention.
- Preserve defensive-timeout precedence and stopped/terminal/penalty/kick exclusions. Never spend both teams' timeouts on one event. The shared three-timeout budget per team/half and halftime reset remain unchanged.

The FG-range reservation makes clock available but leaves the existing fourth-down-only FG selection unchanged; this trial does not add an any-down end-half FG substitution policy.

These rules were specified from the V4 event-state audit before examining V5 results. No sweep, interpolation or refit to the 2024 aggregate targets is performed. The 50-second threshold, reserved last timeout and runoff guard are tested as one combined intervention, so individual effects are not identified.

## Verification and research gate

43 focused tests pass, including all previous 38. New tests cover actual-call timestamp cutoff, early/late-down reservation, final FG transition, required down context, passive tracing and zero-runoff timeout exclusion. V4 remains separately selectable and reproduces a recorded saved 512-draw batch exactly after the V5 extension.

Retain all five predeclared screens: +/-1 snap/game for each half, +/-0.5 defensive timeouts/game for each half, and +/-0.5 Q2 offensive timeouts/game. Exact 3,600-second accounting and the complete 285 labels / two 512-draw batches per label are required. Passing qualifies only a frozen comparative research baseline; it does not validate the full model or authorize main/production/2025 changes. Full-game snaps, drives and points remain reported separately.

If the gate passes, freeze the exact driver/input/candidate hashes and run Baseline, Fourth-Down-Only, Explosive-Run-Only and Combined. The baseline draws are reused exactly. The fourth-down model is context-dependent; 81.3% describes its neutral midfield-short slice. The rushing switch applies the entire frozen empirical distribution (body plus tail), not a pure explosive-tail perturbation. No candidate refitting or live DFS performance claim is allowed.

Run `scripts/validate_nfl_late_half.py --out late-half-v5-results`, then only after qualification `scripts/replay_nfl_four_arm_research.py --baseline late-half-v5-results --out four-arm-v5-results`.

## Clock-slice qualification

All five predeclared screens pass on 285 labels / 291,840 regulation trials: Q2 snaps 10.268 versus 9.453, Q4 snaps 6.562 versus 6.786, Q2 defensive timeouts 1.220 versus 1.372, Q4 defensive timeouts 0.794 versus 0.965, Q2 offensive timeouts 1.464 versus 1.502. Maximum ledger error zero; 43 focused tests pass. Freeze this exact configuration for the user-authorized four-arm research matrix. Q2 snap bias remains +0.816/game despite the coarse screen passing.

Full-game snaps 130.341 versus 123.660 (+5.4%), drives 24.082 versus 21.267 (+13.2%), and points 40.092 versus 45.754 (-12.4%) still fail the separate 5% screens. Therefore the full-model baseline is NOT validated and no main merge, production change or 2025 evaluation is permitted. The lock applies only to the comparative research configuration.

## Completed comparative matrix

All four arms completed 285 labels / two seeds / 512 draws per seed (1,167,360 total arm outcomes), reusing the 570 baseline batches exactly. All arm ledger errors are zero. Baseline points/punts: 40.092 / 10.773; Fourth-Down-Only 41.398 / 9.478; Explosive-Run-Only 39.546 / 11.419; Combined 40.882 / 9.936. Fourth-down-only has the strongest scoring/punt effect in this driver. The full rushing candidate restores 20+ gains but worsens aggregate scoring and punts; the switch is not tail-only. All arms still fail full-game volume/scoring screens. No promotion, merge, production changes or 2025 evaluation.
