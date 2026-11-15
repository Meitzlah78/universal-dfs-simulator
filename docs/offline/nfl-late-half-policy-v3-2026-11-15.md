# UNVALIDATED RESEARCH — NOT READY TO MERGE TO MAIN

Policy `late-half-management-v3`. Production and main remain unchanged. 2025 PBP is not extracted or read. The previously reviewed v2 source, 29 tests and notes were published to `codex/nfl-late-half-baseline` at commit `1adf82f6226e6652deabcfe817ba6d28e76966cf`; its tree exactly matches the locally reviewed v2 source tree. Git HTTPS lacked credentials, so publication used the connected GitHub account.

## Frozen Q2 intervention

In the final 120 seconds of Q2, after a nonterminal live running-clock offensive play, use urgency when the offense is past its own 20 (distance to opponent goal < 80) and leads by fewer than 21 points. This includes every trailing score and a tie. Cap the interval at 20 total seconds including live time. Existing faster sampled intervals are preserved. No override applies to stopped-clock, scoring, possession-changing, penalty or kick events.

During the final 45 seconds, the same eligible offense uses an available timeout if the defense has not already stopped the clock and at least five live seconds remain in the half. A timeout replaces the interval with five total seconds. Do not spend both teams' timeouts on one event. Track offensive and defensive timeout counts separately. Three timeouts per team per half remain shared across each team's offensive and defensive use; the existing halftime reset remains in place.

The 20-second cap and 45-second timeout trigger were specified before this v3 replay. They are exploratory policy assumptions, not estimates or a sweep fitted to reach 9.45 snaps. The territory and score gates implement the user's requested rule. Field position is evaluated after the live play, preparing its outgoing interval. Q4 policy remains v2, although changed Q2 outcomes can affect Q4 states and aggregate results.

The ordinary play-call/outcome inputs, rushing distribution candidate and fourth-down candidate remain frozen. No tuning or 2025 reads are allowed. A recorded 512-draw v2 batch reproduces every old metric with the extended driver.

## Research gate and arm definitions

The user's requested Q2/Q4 snap and defensive-timeout screens, plus exact 3,600-second regulation accounting, control whether the exploratory matrix may run. Existing tolerances remain +/-1 snap and +/-0.5 defensive timeouts per half. This is a clock-slice qualification for comparative research, not full-game or production validation. Full-game snap/drive/point screens remain reported even if they fail. A passed slice gate does not permit a merge or open 2025.

`research_baseline_locked` distinguishes a frozen research comparison configuration from a fully validated baseline (`baseline_locked`, still false). The four-arm runner checks the gate, policy, all source hashes, exact frozen inputs, candidate hashes, and complete 285-game/1,024-draw baseline batches before starting. Baseline draws are reused exactly; three intervention arms use identical game-keyed seeds and fixed-width event-index streams. Paths need not remain state-aligned after interventions.

- Baseline: frozen reconstructed ordinary outcome kernel with v3 management.
- Fourth-Down-Only: replace only the fourth-down decision policy with the frozen 2022–2023 candidate.
- Explosive-Run-Only: apply the frozen, body-adjusted empirical rushing candidate. This switches the full rushing distribution, body plus tail; the label does not imply a pure tail-only intervention.
- Combined: apply those same two frozen candidates together.

All arms are league-level simulations keyed by 285 historical game labels, not matchup/player-calibrated forecasts. 2024 is repeatedly reused development data, not an independent validation set. A matrix result cannot establish DFS lineup/selector improvement or live readiness.

Run validation with `scripts/validate_nfl_late_half.py --out late-half-v3-results`, using the saved frozen inputs and 2024 PBP. Only a passed research gate allows `scripts/replay_nfl_four_arm_research.py --baseline late-half-v3-results`. Failed gates block before any candidate replay.

## Measured outcome

FAIL: Q2 snaps 11.071 versus 9.453 observed. Q4 snaps 6.568 versus 6.786. Defensive timeouts Q2 1.267 versus 1.372 and Q4 0.796 versus 0.965 pass the existing screens. Offensive Q2 timeouts 1.945 versus 1.502 observed. Full-game snaps 131.145, drives 24.200, points 40.182; all full-game screens fail. Maximum ledger error is zero. 34 focused tests pass. The real four-arm entry point rejects the failed gate before candidate replay. No baseline lock, ablations, production changes or 2025 evaluation.
