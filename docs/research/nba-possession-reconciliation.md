# NBA full-possession reconciliation — November 13, 2026

Offline development evidence, draft PR #77. No production import, model parameter, minutes sampler, role-blending policy or roster fallback changes. Same frozen 226-game conditional comparison set; original unsupported roster game 401909909 stays excluded/unresolved. These games use observed eligible rosters/minutes, not verified pregame forecasts.

## Completed checks

Five boundary-clean games, two arms, 128 draws per game/arm passed the final-clock-tail smoke check before the full replay. All 452 arm/game records complete without failures. Per-game checkpoints and four disjoint deterministic shards preserve the original game indices/seeds and earlier-date priors. Adding counters reproduces the prior hazard replay's per-game points/FGA/FTA/player OREB/DREB means exactly (maximum difference zero). Every simulated elapsed-time ledger reconciles to within 3.64e-12 seconds. All 404 NBA tests pass, one skipped; five new tests cover source boundaries and unchanged simulator draws. The first broad test attempt lacked restored app dependencies; the completed suite was rerun after restoring them.

## Primary comparison: 145 boundary-clean games

“Boundary-clean” means no unresolved control-change/clock flags in this parser, not independently certified official possession counts. All 145 source clock partitions conserve regulation plus overtime exactly, and all 226 games reconcile scoring. Positive-clock period-ending control is included as a terminal possession; terminal durations remain separate from completed possessions. Ordinary offensive rebounds continue possession; an and-one trip is associated with its made basket. Retained-ball special cases remain approximate.

| Metric | Observed | Clock reference | Foul + rebound candidate |
|---|---:|---:|---:|
| Combined possessions/game | 202.21 | 221.13 | 217.92 |
| Team pace per 48 minutes | 100.74 | 110.29 | 108.69 |
| Seconds per counted possession (OT included) | 14.29 | 13.06 | 13.25 |
| Points/game | 227.57 | 251.47 | 254.66 |
| Points per 100 possessions | 112.54 | 113.72 | 116.86 |
| FGA/game | 175.49 | 181.46 | 191.38 |
| FTA/game | 50.58 | 62.31 | 52.44 |
| eFG% | 53.69 | 55.80 | 55.76 |
| TOV% per possession | 15.81 | 14.70 | 15.21 |
| OREB% | 27.15 | 25.74 | 27.61 |
| FTr (FTA/FGA) | 0.2882 | 0.3434 | 0.2740 |

The combined candidate overshoots by **27.10 points/game**. A symmetric arithmetic decomposition assigns **18.02 points to possession volume** and **9.07 to points per possession**. This is an identity, not a causal estimate of what a timing patch will remove: timing changes event opportunities, shot-clock support and scoring jointly. Re-run any pace change before claiming an improvement.

## Full completed-possession elapsed time by start

These are start-to-end durations, including ordinary OREB continuations, not just the next-action interval. End-of-period terminal possessions are excluded from this table and retained separately in JSON. OREB continuation tails overlap these durations and must not be added to the clock ledger.

| Start | Observed seconds | Candidate seconds | Candidate minus observed | Observed / candidate completed count per game |
|---|---:|---:|---:|---:|
| after_make | 16.74 | 15.35 | -1.39 | 74.46 / 84.70 |
| after_dreb | 12.91 | 12.33 | -0.58 | 63.03 / 65.53 |
| after_turnover | 10.75 | 10.43 | -0.33 | 31.14 / 32.67 |
| dead_ball_inbound | 15.52 | 9.96 | -5.56 | 5.03 / 5.19 |
| after_ft | 15.50 | 14.45 | -1.05 | 20.51 / 21.62 |
| period_start | 17.73 | 10.20 | -7.53 | 4.03 / 4.02 |
| after_andone_oreb | 6.63 | 6.13 | -0.50 | 0.17 / 0.17 |

The largest common-start gap is after a make; period starts and the smaller dead-ball restart cohort are especially short. “Dead-ball inbound” is a control-restart proxy based on team defensive rebounds/known restarts; explicit inbound-touch timestamps are not available, so this is not an isolated measured inbound delay. Start-mix and outcome selection differ between arms; bucket means alone do not identify a clean causal seconds adjustment.

The ordinary player-OREB continuation tail is **6.35s observed versus 6.39s candidate**. Uniform rebound-flight padding is unsupported: saved miss/rebound events have coincident timestamps. Period-start and team/dead-ball state handling deserve separate investigation before applying any global pace factor. Code inspection confirms that quarter starts and team-rebound restarts both use the shared `other` action-time profile rather than dedicated restart profiles. The legal-action sampler also conditions next-action intervals on remaining shot-clock support; reconstructing full control durations is therefore necessary before treating that truncated interval distribution as calibrated pace. These are isolated next hypotheses, not measured fixes.

## Shooting decomposition

| Component | Observed | Candidate |
|---|---:|---:|
| 2PT FG% | 53.93% | 55.47% |
| 3PT FG% | 35.59% | 37.45% |
| 3PT attempt share | 43.42% | 41.48% |
| FT% | 77.32% | 78.63% |

Symmetric decomposition of the **+2.068 percentage-point eFG gap**: **+0.885pp from 2PT conversion**, **+1.185pp from 3PT conversion**, and **−0.002pp from attempt mix**. Excess three-point attempt share is not the cause. Current shot probability combines player splits and a team efficiency scale; it has **no explicit remaining-shot-clock (<4s) efficiency penalty**. The archive does not supply an independently verified full shot-clock state, so no measured empirical late-clock penalty or attributable point effect is claimed. That requires reset-aware reconstruction and earlier-game fitting.

## Full-set sanity check and source limitations

| Metric | Observed 226 | Candidate 226 |
|---|---:|---:|
| Combined possessions/game (source provisional) | 203.42 | 218.12 |
| Points/game | 227.35 | 255.18 |
| ORtg (source provisional) | 111.76 | 116.99 |
| FGA/game | 175.49 | 191.46 |
| FTA/game | 52.00 | 52.75 |
| eFG% | 53.34 | 55.81 |

The 81 flagged games remain flagged, with 111 unexplained-control-change and 46 left-censored row flags. The full-set possession/ORtg values are provisional sanity checks, not primary exact pace results. One flagged source game has a one-second clock-partition discrepancy. Official team box totals supply Four Factors; all 226 source scoring totals reconcile.

Three boundary-clean games have one-count PBP turnover discrepancies against official totalTurnovers (401909853, 401909867, 401909894). Keeping the locked 145 slice and separately excluding those three gives a 142-game sensitivity: **202.09 observed vs 217.89 candidate possessions; 112.50 vs 116.88 ORtg**. The diagnosis is unchanged. The extra 81 games and all rate denominators are reported explicitly rather than silently repaired.

## Definitions

- Combined possessions count both teams; team pace normalizes half that count to 2,880 seconds, including OT exposure.
- ORtg = 100 × points / combined possessions, using aggregate totals across matched games/draws.
- eFG% = 100 × (FGM + 0.5 × 3PM) / FGA.
- TOV% shown = 100 × official/model total turnovers / possessions. JSON also includes the distinct box-exposure convention, TO / (FGA + .44 FTA + TO).
- OREB% = credited offensive rebounds / (credited offensive + defensive rebounds), aggregating both teams. Team/dead-ball rebounds are not player fantasy rebounds.
- FTr = FTA/FGA. The box proxy FGA + .44FTA − OREB + TO is kept separate from event-derived possession counts.
- Four-Factor ratios use aggregate counts, not unweighted averages of game percentages.

## Next isolated experiment

Audit conditional timing and clock-state transitions first, concentrating on after-make, opening-period and team/dead-ball restart states. Hold minutes variance, archive blending and unsupported-roster handling fixed. Evaluate possessions and ORtg jointly on this development set; do not assume a uniform time increase will preserve efficiency. Then isolate conversion calibration/late-clock shot selection under the corrected pace. No promotion is supported by these results.

## Reproduction

```
PYTHONPATH=.:tests python scripts/replay_nba_possession_reconciliation.py REPO EVIDENCE SMOKE_OUT 5
PYTHONPATH=.:tests python scripts/replay_nba_possession_reconciliation.py REPO EVIDENCE SHARD_OUT 0 0/4
# Repeat disjoint shards 1/4, 2/4, 3/4; keep the original game index/seeds.
PYTHONPATH=.:tests python scripts/summarize_nba_possession_reconciliation.py REPO EVIDENCE RESULTS
```

For this corpus, summarization expects sibling nba-possession-shard-0 through -3 directories and the original sibling nba-hazard-resume checkpoint for unchanged-draw verification. Smoke selection expects the frozen source-traces.json in sibling nba-possession-results. These scripts are scoped research tooling, not a generic public replay API.
