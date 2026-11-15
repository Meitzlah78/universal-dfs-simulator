# UNVALIDATED RESEARCH — NOT READY TO MERGE TO MAIN

Policy `late-half-management-v4`. This tests the requested Q2 field/clock revision. Production, main, frozen candidates and 2025 remain untouched. Repeatedly inspected 2024 data remain development evidence, not a new independent validation set.

## Frozen v4 rules

Apply the beyond-own-35 condition (distance to opponent goal < 65) to the shared Q2 urgency eligibility and offensive timeout eligibility. Preserve the existing final-120-second urgency window, margin below +21, nonterminal running-clock requirement and 20-second total interval cap. The offense need not be trailing. On an eligible play, use an available offensive timeout only when half time remaining <= 70 seconds and > 5 seconds, with no defensive timeout already stopping the play. Live time is included, not added again. Preserve the existing shared three-timeout team budget and halftime reset.

The 70-second cutoff expands v3's 45-second window. The field restriction is stricter than v3's own-20 gate. Both changes are explicit; do not describe the clock change alone as tighter. The shared field gate is applied after the live play to its outgoing interval. No sweep, interpolation or fitted correction to the 2024 aggregate targets is performed.

Q4 policy, safe kneel horizon, ordinary play-call/outcome model, frozen clock distributions and the two candidates remain unchanged. Altered Q2 results can still change later Q4 game states. Preserve v3 as a selectable policy for exact regression comparison.

## Predeclared research gate

Keep the existing +/-1 snap/game per half and +/-0.5 defensive timeout/game per half screens. Add the user's Q2 offensive timeout objective using the same +/-0.5 event/game screen around its observed 1.50175 mean. Exact 3,600-second accounting is required. The user-authorized four-arm research matrix may run only if all five screens pass on the complete 285 labels / two seeds / 512 draws per seed. The extra offensive-timeout check is declared before this v4 result is examined.

This freezes a clock-slice-qualified research configuration, not a production or fully validated NFL model. Full-game snaps, drives and scoring remain measured even if they fail. No merge or 2025 evaluation is allowed. The four-arm runner verifies the exact source/input/candidate hashes and all 285 baseline batches before any intervention replay.

Arm definitions remain unchanged: Baseline; frozen Fourth-Down-Only candidate; frozen empirical rushing candidate under the label Explosive-Run-Only; Combined. The rushing switch changes the complete frozen distribution, body plus tail, rather than isolating only 20+ gains. Models are not refit. Baseline draws are reused exactly; intervention arms share game-keyed seeds and fixed event-index streams.

## Verification

38 focused tests pass: 21 existing offline tests, 14 management/benchmark tests, and three matrix-gate tests. New tests cover strict own-35 eligibility, the inclusive 70-second cutoff, half-end/Q4 exclusions, timeout budget and defensive-stop precedence, and rejection of absent/failed offensive-timeout evidence. The extended driver also reproduces every saved v3 metric in a recorded 512-draw batch.

Run `scripts/validate_nfl_late_half.py --out late-half-v4-results` using the saved frozen inputs and original 2024 PBP. Only after a passed research gate, run `scripts/replay_nfl_four_arm_research.py --baseline late-half-v4-results --out four-arm-v4-results`.

## Measured outcome

FAIL: Q2 snaps 10.615 versus 9.453 observed; Q4 snaps 6.559 versus 6.786. Defensive timeouts Q2 1.166 versus 1.372, Q4 0.793 versus 0.965. Offensive Q2 timeouts 1.963 versus 1.502 observed, slightly above v3's 1.945. Only Q2 snaps fail the five coarse slice screens. Full-game snaps 130.682, drives 24.140, points 40.169; all full-game screens fail. Ledger error zero; 38 focused tests pass. The actual four-arm entry point rejects this failed gate before candidate replay. No baseline lock, matrix, merge, production change or 2025 evaluation.
