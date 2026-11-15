# NFL rebuilt-driver policy diagnosis — November 14, 2026

Offline only. Production unchanged; 2025 not opened; event-lever four-arm ablations remain blocked.

## Scope and instrumentation parity

First ten lexically sorted 2024 games, two seeds and 512 draws per seed (10,240 trials). All 20 instrumented batches exactly preserve the previously saved rebuilt means, clock seconds and ledger errors. This is a diagnostic subset, not a fresh validation set.

## Clock counts and durations

| Clock class | Archived events/game | Rebuilt events/game | Archived seconds/event | Rebuilt seconds/event |
|---|---:|---:|---:|---:|
| running | 86.6508 | 83.8994 | 33.3791 | 35.0339 |
| incomplete | 24.1648 | 23.5630 | 4.9150 | 4.9214 |
| out_of_bounds | 13.1835 | 12.0752 | 28.2935 | 28.9144 |
| changed | 7.4986 | 7.2903 | 4.9624 | 4.9793 |
| kick | 15.2530 | 14.6448 | 6.9704 | 6.9761 |
| penalty | 10.0431 | 9.6740 | 4.9822 | 4.9858 |

The running-clock duration difference is approximately +1.65 seconds/event. This localizes the discrepancy but does not prove its cause: game-state mix, timeout handling, management and interval selection all remain possible contributors. No clock padding was fitted. Archived management events (kneel/clock management) and rebuilt timeout events have different meanings and must not be treated as interchangeable categories.

## Input-rate restoration on identical seeds

| Configuration | Snaps/game | Drives/game | Points/game |
|---|---:|---:|---:|
| Archived league | 132.68076 | 24.58213 | 41.64639 |
| Rebuilt unchanged | 128.61484 | 23.81660 | 39.80107 |
| outcome_rates_restored | 128.41992 | 23.75752 | 39.90371 |
| clock_rates_restored | 128.94385 | 23.86377 | 39.83037 |
| both_rate_sets_restored | 128.75059 | 23.80371 | 39.94199 |

Restoring both archived rate sets increases snaps by only 0.13574/game; the archived-versus-restored gap remains 3.93018 snaps/game. This is not the learned fourth-down/explosive-run ablation matrix. These tests restore archived input constants while leaving policies and event mechanisms unchanged.

## Specific reconstruction differences

- Rebuild uses one pooled OOB probability for runs and completions; archive records separate oob_run and oob_pass rates
- Rebuild uses 0.07 no-play penalty hazard; archive records 0.06394778040173003 and defensive penalty share; rebuild consumes time but applies no penalty field/down movement
- Rebuild re-estimates several outcome rates with different event filters instead of reusing exact archived learned_parameters
- Rebuild lacks archived two-point conversions, defensive return TDs and explicit management/kneel events
- Rebuild timeout use is Q4 final120 only; recovered clock model also has end-Q2 profiles; original explicit timeout policy source remains unavailable
- Same raw seed integers do not imply same random streams: rebuilt hashes game and seed and allocates fixed 14-uniform event blocks; archive labels streams non-event-aligned, implementation unavailable

Fourth-down strict inside-five and final-180-second trailing triggers match the available baseline rule; the 40-yard distance-to-goal FG threshold, own-25 kickoff and seven-second punt/FG duration also match the available constants. Full historical policy and RNG parity cannot be established without source. Same seeds alone cannot recover random draw ordering.

## Pass/run and stopping-rate availability

Rebuilt dropbacks/game 76.55752; designed runs/game 52.05732; dropback share 59.525%. Incompletions/game 23.80244; completions/game 45.91475; sacks/game 5.19775.

The archived LEAGUE baseline does not retain pass/run counters. The later tail audit contains HYBRID counters only. Therefore the exact league pass/run-ratio comparison is unavailable, rather than inferred by mixing arms. Ledger incompletion counts are available but differ from pre-terminal incomplete-pass counts when fourth-down failure changes the terminal class.

## Rushing calibration boundary

The training-only body correction remains unchanged: 2024 conditional YPC 4.25861 versus 4.33906 observed, with 20+ probability 2.14864% preserved. Its training mean target is 4.28561 from 2022–2023. Moving parameters specifically to hit 2024 4.34 would be additional tuning, not a training-only correction. No such adjustment was made.

## Next prerequisite

Restore or independently specify and validate timeout, hurry-up, kneel/management, penalty movement and omitted scoring mechanisms before baseline equivalence or full event-lever ablations. The original implementation cannot be certified from aggregate summaries alone; do not tune to rounded archived averages.

21 standalone component/accounting tests pass, including audit count identities and prior holdout guards. Executable changes are preserved on the offline research branch.
