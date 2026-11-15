# UNVALIDATED RESEARCH — NOT READY TO MERGE TO MAIN

Version: `late-half-management-v2`. Production is untouched. 2025 PBP remains locked. Four-arm event-lever ablations remain blocked until a baseline is validated. This branch records exploratory policy changes and failed trials; it does not promote a live model.

## Frozen changes for this trial

- Defensive timeouts on otherwise running, nonterminal plays require a defense trailing by 1–8 points in the final two minutes of Q2/Q4, an available timeout, and enough time for the live play to finish. The prior trial allowed 1–16 points.
- Q4 victory formation is allowed only with a positive lead, 0 < remaining <= 120 seconds, downs 1–3, sufficient field to avoid a safety throughout the sequence, and enough remaining downs to exhaust the clock even if the defense uses its available close-game timeouts. With `a = 4 - down` available kneels and `t` effective defensive timeouts, the horizon is `2*a + 40*max(a-t, 0)` seconds. Each kneel takes two live seconds plus up to 40 seconds runoff; a defensive timeout removes that runoff. A lead greater than eight points assumes the defense concedes clock and does not call additional timeouts. This is an explicit exploratory assumption.
- Kneels count as offensive snaps and separate management events. They lose one yard, advance the down, and do not enter ordinary rushing-efficiency/tail estimates. Kneels have no stochastic fumble/penalty process in this research trial.
- The extra 12-second cap from v1 is removed. The unchanged 2022–2023 empirical clock profiles already distinguish late-half scripts; v2 samples those profiles intact. This is not a refit of clock durations to 2024 targets. Hurry eligibility is recorded, but there is no additional hurry timing override.

The ordinary play-call model, outcome parameters, fixed kickoffs, rushing candidate and fourth-down candidate remain frozen. No candidate is applied to the proposed baseline. This combined trial cannot isolate individual effects of narrower margins, kneels and removal of the extra hurry cap.

Rules were specified after seeing v1's reused-2024 diagnostic failure, before v2's replay. All new measurements remain development/tuning evidence, not an independent holdout. Existing screens remain unchanged: +/-1 snap per half, +/-0.5 defensive timeouts per half, and 5% full-game volume/scoring errors. Passing these screens would still require scrutiny of missing offensive management and state-conditioned behavior.

## Verification

Unit tests exercise both half boundaries, one-possession margin limits, safe kneel horizon across remaining clock and timeout budgets, stopped/terminal precedence, deterministic replay, snap accounting including kneels and full regulation clock conservation. A recorded 512-draw v1 batch was replayed with the extended driver; every prior mean, audit, ledger and late-half metric matched exactly.

The 285 labels select game-keyed random seeds for a league model; they are not matchup-conditioned forecasts. Two seeds and 512 outcomes per seed give 291,840 regulation trials. No 2025 member is extracted or read.

Use `scripts/validate_nfl_late_half.py --out late-half-v2-results` with the prior saved frozen inputs and original 2024 PBP. Results and final gate decision are in the separate validation artifact.

## Measured decision

Q2 snaps 7.664 versus 9.453 observed (FAIL); Q4 snaps 6.584 versus 6.786 (PASS). Defensive timeouts Q2 1.109 versus 1.372, Q4 0.806 versus 0.965 (both pass existing +/-0.5 screens). Q4 kneels 1.278 versus 1.161 observed. Full-game snaps 127.769, drives 23.625, points 38.799; drive/scoring screens fail. Maximum ledger error zero; 29 focused tests pass. Baseline remains unvalidated; ablations remain blocked. No source push or merge completed.
