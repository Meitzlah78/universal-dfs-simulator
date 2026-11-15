# NFL corrected-clock reconstruction and rushing-body checkpoint

Offline research only. Production unchanged; 2025 not opened; gates remain draft. November 14, 2026 (Eastern).

## Decision

The reconstructed clock conserves regulation time but FAILS archived-baseline equivalence. Four-arm ablations were not run. This is a new exploratory league-level driver, not recovery of the original implementation. It is not ready for live builds.

## Rushing body: training-only correction

Fit: 27,601 designed runs from 2022–2023. Training observed YPC 4.28561; expected before 4.21609, after 4.28561. Only gain buckets 1–6 change; every probability outside this body remains exactly unchanged.

| 2024 conditional metric | Previous empirical model | Body-adjusted | Observed |
|---|---:|---:|---:|
| Mean rushing yards | 4.18925 | 4.25861 | 4.33906 |
| Runs 20+ (%) | 2.14864 | 2.14864 | 2.23285 |

The remaining YPC deficit is approximately 0.08 yards. The 2024 value was not used as a fitting target. No force-fit to 4.34 was made. These are conditional checks on actual field positions, not full-game player or market calibration.

## 285-game baseline reconstruction

Two seeds, 512 draws per seed: 291,840 regulation game trials. Per-game checkpoints are included.

| Metric | Archived corrected league baseline | Reconstructed driver | Difference |
|---|---:|---:|---:|
| snaps | 132.68083 | 128.62535 | -4.05548 |
| drives | 24.58176 | 23.83018 | -0.75157 |
| points | 41.58245 | 39.73253 | -1.84991 |

Reconstructed punts/game: 10.57560; non-red-zone offensive TDs/game: 0.44606. These are reconstruction diagnostics, not improvement claims or event-lever ablation results.

Maximum absolute clock-ledger error: 0.0000000000 seconds. Every trial accounts for 3,600 regulation seconds. Period boundaries, halftime possession reset, outcome-conditioned intervals and warning interruption are implemented. Accounting conservation does not establish calibrated clock behavior.

| Clock class | Reconstructed seconds/game |
|---|---:|
| running | 2938.21550 |
| incomplete | 116.23223 |
| early_out_of_bounds | 337.28085 |
| late_out_of_bounds | 12.50482 |
| changed | 36.23801 |
| kick | 102.35500 |
| penalty | 48.24511 |
| timeout | 8.92847 |

## Known differences and next prerequisite

- League-level event driver without original player usage allocation
- Approximate penalties and timeout policy
- No separate scramble process, defensive return TDs or two-point conversions
- Fixed own-25 kickoff, zero kickoff clock unchanged
- No certified market/weather/player calibration

The original player allocation, clock-management policy, outcome mechanisms and random-stream implementation remain unrecovered. Compare these mechanisms before claiming exact baseline equivalence; do not tune clock padding or scoring to the archived averages. If an explicitly new baseline is pursued, it requires its own independent verification before event-lever comparisons.

## Source and tests

Executable source is preserved on GitHub branch `codex/nfl-event-levers-offline`, implementation commit `fd6044ed84902c74996cf37ed34a042bc6f7b7f3`. No merge or deployment.

35 local tests pass (new component/rebuild tests plus existing situational/clock checks). All 21 new tests also pass from a clean checkout of that GitHub commit. Source hashes and exact input hashes are recorded in the result JSON.

Run from repository root:

    OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python3 scripts/rebuild_nfl_clock_checkpoint.py /path/to/pbp /path/to/prior-checkpoint /path/to/output --draws 512

The prior-checkpoint directory supplies the recovered clock JSON, original checkpoint ZIP, and event-levers gain models; its sibling situational-results directory supplies tuning.json. This dependency on recovered artifacts is explicit. Source hashes alone cannot recreate missing historical source.
