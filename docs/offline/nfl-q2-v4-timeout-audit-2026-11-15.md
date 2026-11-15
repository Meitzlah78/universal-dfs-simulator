# Passive V4 Q2 offensive timeout audit

Research only; main/production unchanged, 2025 not opened. Replay all 285 2024 labels, two seeds, 512 draws each with a passive callback. Every returned dictionary matches every one of the 570 saved V4 batches exactly. The callback does not draw random numbers or change state.

572,812 offensive calls / 291,840 regulation trials = 1.9627604 calls/game. The trace retains exact pre-snap and timeout-call clock values, before/after field position, pre/post-play down, score margin, both budgets and sampled/hurry intervals for every call.

| State | Offensive calls/game |
|---|---:|
| Actual call clock >50 to 65 seconds | 0.54335 |
| Call clock >45 to 50 seconds | 0.25279 |
| Call clock >30 to 45 seconds | 0.49460 |
| Call clock >15 to 30 seconds | 0.36006 |
| Call clock 1 to 15 seconds | 0.31196 |
| Last timeout spent with next down 1 or 2 | 0.33808 |
| Outside the driver's FG range (distance >40) | 0.98713 |

141,829 calls had only one timeout left (0.48598/game); 12,373 calls had a sampled/hurry interval <=5 seconds, providing no positive runoff saving under the driver's five-live-second convention. Budget and clock/field counts overlap; do not add them as independent causal effects.

V4's 70-second threshold used pre-snap clock. Fixed five live seconds place the actual calls at 1–65 seconds. V5 should define its threshold at the timeout-call timestamp explicitly. The broad trigger has no last-timeout reservation and does not check whether the interval contains outgoing runoff.

This is an exact synthetic-driver trace, not observed NFL timeout behavior or independent 2024 validation. Full event CSVs and summary are retained in the audit artifact. Subsequent changes must preserve this selectable V4 policy and its replay results.
