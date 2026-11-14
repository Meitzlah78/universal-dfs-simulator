# NBA minutes-role audit and expanded offline evidence — 2026-11-14

Production and PR #77 remain untouched. The shared-bench policy is unchanged; this is retrospective development evidence, not a prospective promotion holdout.

## Scope
12 saved builds on six dates: 1,627 player forecasts across 39 physical games. Two overtime games are excluded from regulation-minute scoring, leaving 37 games. Latest pretip team snapshots deduplicate DK/FD for the primary dependence comparison: 36 games and 334 bench pairs. Missing actuals are omitted explicitly; no absence-to-zero imputation. New fantasy scores are reconstructed ESPN boxscore scores, not settled site payouts.

## Original >5-minute miss diagnosis
Fantasy 80% interval coverage:

| Pregame minute tier | DK | FD |
|---|---:|---:|
| Bench <18 |47.8%|41.9%|
| Rotation 18–<28 |34.6%|38.9%|
| Core >=28 |45.8%|39.3%|
| All tiers |43.2%|40.2%|

Regular/core players account for 62.5% DK and 60.9% FD of uncovered intervals among these misses. Core misses are downward in 42/48 DK and 50/56 FD cases. Bench minutes are underpredicted on average while core/rotation minutes are overpredicted. Minute tiers and archived expected-starter flags are reported separately; tiers are not retrospective starter labels. Final fouls and margins are context proxies, not causal diagnoses. Late-news timestamps are unavailable.

## Expanded results under unchanged policy
>5-minute miss coverage remains poor: DK 44.0% (259 rows), FD 42.4% (288). Shared dependence alone cannot repair forecast centering.

Observed bench co-spike rate: 9.58%; independent prediction 3.76%; shared prediction 15.17%. Game-cluster Brier delta -0.00971 (95% interval -0.02694 to +0.00578); logloss delta -0.08690 (-0.20146 to +0.01101). Both intervals include zero. Site-specific Brier worsens on DK (0.07176 to 0.07554) and improves slightly on FD (0.09220 to 0.09109). Minute marginal coverage remains 73.52% in both arms. No retuning or promotion is supported.

## Reproduction
Run scripts/expand_minutes_evidence_offline.py, scripts/audit_minutes_miss_roles_offline.py, then scripts/audit_shared_bench_offline.py with --extra-forecast. Inputs and hashes are recorded in expansion.json and expanded_shared/summary.json in the accompanying report. Tests: 17 passed, including cutoff, duplicate, alias, interval, marginal and production-equivalence checks.

Next modeling priority is pregame minute centering and realistic downside/availability rotation states, alongside shared bench dependence; blanket fantasy-rate widening is not justified by this audit.
