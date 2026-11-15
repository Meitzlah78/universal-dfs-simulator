# Exploratory late-half clock management — November 14, 2026

Offline only. This proposes a new baseline rather than certifying archived-driver parity. No production change, no 2025 extraction/evaluation, no candidate parameter changes.

The policy is versioned `late-half-management-v1`. Evaluate it after a nonterminal live offensive play whose clock would otherwise keep running. In Q2/Q4 with 0 < half time remaining <= 120 seconds, a defense trailing by 1–16 points uses an available timeout (five total live seconds, no additional runoff). A trailing offense down 1–16 points, or a tied offense at most 60 yards from goal after the play, uses a hurry-up interval capped at 12 total seconds. Timeout takes precedence; management cannot override stopped or terminal plays. All times include live time. No additional kickoff/PAT clock deductions are introduced.

Rules were frozen before measuring 2024. Acceptance checks are exploratory: within 1 snap/half and 0.5 defensive timeouts/half on league means. Full-game snaps, drives and points are also checked against a 5% relative-error screen. These screens do not establish independent validation or production readiness. The same 2024 season has been inspected repeatedly. Explicit offensive timeouts, kneels and spikes are still absent from this candidate driver, and they must remain visible in the benchmark.

The benchmark includes kneels and spikes, which have dedicated PBP play types. Timeout rows often omit possession; classify them only if the same game/quarter/fixed-drive has one unambiguous recorded offense and defense. Preserve unresolved events. Snap starts at exactly 120 seconds are included; starts at zero are excluded from the two-minute slice. Zero-event games remain in every denominator.

Run 285 regulation game labels with two seeds and 512 draws per seed (291,840 trials). These are league-level simulations with different game-keyed seeds, not matchup-conditioned historical forecasts. Preserve the frozen ordinary decision model, outcome parameters and 2022–2023 clock distributions. The rushing and fourth-down candidates remain external and unapplied to this proposed baseline. Their hashes are recorded separately. The four-arm matrix requires successful baseline validation and is not authorized by a component-test pass.

Reproduce with the saved frozen inputs and original 2024 PBP:

    OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python3 scripts/validate_nfl_late_half.py --data /path/play_by_play_2024.csv.gz --frozen /path/frozen_inputs.json --actual-audit /path/Simmah_2024_Full_Game_Hybrid_Replay.zip

The output directory is `late-half-results`. Cached simulation batches require matching driver/input/policy/seed hashes. Remove the directory's batches and cache metadata for a fresh replay. The artifact report contains measurements and the final decision.

## Measured decision

All four slice checks failed. Proposed snaps/game 135.348 versus 123.660 directly counted; drives 24.934 versus 21.267; points 42.107 versus 45.754. Clock ledger error remains zero. The new policy is rejected as a baseline; all event-lever ablations remain blocked. 26 focused tests pass.
