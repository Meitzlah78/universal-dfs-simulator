# Coupled minutes: game-script audit and bounded kernel

2026-11-14. Offline branch only. Production and PR #77 untouched.

## Retrospective audit
The 1,627 forecast rows contain 136 deduplicated non-OT core/rotation losses exceeding five minutes across 37 games (73 core, 63 rotation). Latest pretip team snapshots avoid counting DK/FD twice.

- Blowout proxy: 81/136 (59.6%). Final margin >=20 or Q4 6:00 margin >=20.
- Verified foul-threshold proxy: 19/136 (14.0%). Personal-foul PBP count must equal final PF; two by Q1, three by halftime, four by Q3, or six final.
- Both: 10. Neither: 46. Two personal-foul ledgers do not reconcile; no foul attribution for them.
- Competitive proxy: 32 (final and Q4 6:00 margins <=10).
- Thirteen losses are consistent with tightening: competitive game, pregame minute rank >7, loss >5, matched top7 net minute gain positive. This is not confirmed substitution-stint causation.

These are overlapping associations, not mutually exclusive causal buckets. No historical late-news timestamps. Actual outcomes may label diagnostics, never pregame prediction features. The 88–89% statistic referred to the original subset, not a target distribution for every rotation player. The expanded set remains development evidence, not independent validation.

## Implemented prototype
`simmah_nba_coupled_minutes_offline.redistribute` accepts a legal trial rotation, a caller-supplied simulated state, a transfer budget, and optional foul cuts. Blowout transfers top7 minutes to reserves; tight-game transfers ranks8+ minutes to top7; foul cuts transfer to other available players. Every operation conserves 240 minutes, respects [0,48], and reports unsupported transfers. Foul-cut recipients stay excluded from subsequent positive script transfers.

This is a tested redistribution kernel, NOT a fitted probabilistic model or a time-resolved foul-disqualification engine. No probabilities or transfer budgets were selected from these outcomes. No full-game fantasy-coverage improvement has been demonstrated.

## Statistical model design and next gates
1. Correct pregame minute centers using earlier-game-only histories; respect 240-minute rotation budget and documented availability. Do not center on actual minutes from the evaluation game.
2. Draw shared game script once per game from pregame market/context and simulated score trajectories; both teams share blowout/competitive environment, with team-specific recipient support. Avoid independent player blowout draws.
3. Learn transfer magnitudes and recipients from earlier PBP substitution stints, accounting for time remaining, rotation position and availability. Draw foul events on simulated court time; sixth foul removes a player immediately. This kernel only supplies conserved trial totals and cannot replace that mechanism.
4. Allow tight-game concentration, bench expansion, foul-driven redistribution and residual uncertainty; preserve actual game-clock/team-minute consistency. OT requires its own 25 team-minutes per extra period.
5. Fit using earlier games, freeze parameters, then compare independent, shared-only and coupled arms with paired seeds. Evaluate minute MAE/bias and 80% coverage by tier, >5-minute misses, co-spike reliability, and downstream DK/FD fantasy coverage with game-cluster intervals. Report calibration regressions and unsupported rosters. Do not optimize toward a single 9.6% observed rate or condition a production trial on final margins.
6. Twelve builds are development diagnostics. Statistically credible promotion requires genuinely held-out chronological games after design choices are frozen; no promotion based solely on reuse of these builds.

## Uploaded FanDuel standings
Nov13 contest winner 448.0; markmj best405.7. 150 entries, 14 unique rosters, 86 paid entries, $11.90 gross (entry cost not inferred). All154 matched player FPTS agree with reconstructed boxscore scoring to0.01. This confirms that score reconstruction did not drive the Nov13 FD audit discrepancy. No portfolio or simulation was rerun from this file.

21 targeted tests passed; production remains untouched. Full results and row-level labels are in the accompanying audit ZIP.
