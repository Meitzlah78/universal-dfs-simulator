# NBA timing-only restart ablation — November 13, 2026

**Offline / draft PR #77. The pace checkpoint still fails.** Same 145 boundary-clean development games, 128 draws each, original game indices/seeds and conditional rosters/minutes. No changes to shooting probabilities, player priors, hazard fitting, DREB/turnover timing profiles, minutes uncertainty, role blending, or unsupported-roster handling. No late-shot-clock shooting penalty is introduced.

## Measured results

| Metric | Observed | Before | New restart timing |
|---|---:|---:|---:|
| Combined possessions/game | 202.21 | 217.92 | 213.33 |
| Seconds/count (including OT) | 14.29 | 13.25 | 13.54 |
| Points/game | 227.57 | 254.66 | 248.93 |
| ORtg | 112.54 | 116.86 | 116.69 |
| FGA/game | 175.49 | 191.38 | 187.35 |
| FTA/game | 50.58 | 52.44 | 51.06 |
| eFG% | 53.69 | 55.76 | 55.74 |

Possessions drop **4.59/game**, closing about **29%** of the original 15.71-possession excess. **11.12 excess possessions/game remain.** Points drop **5.73/game**, leaving a **21.37-point** surplus. ORtg remains **4.15 points/100 possessions too high**. The earlier +18.02-point arithmetic pace attribution was not a prediction of this patch's causal effect; this replay measures the actual change.

## Full completed-possession durations by start

| Start | Observed seconds | Before seconds | New seconds |
|---|---:|---:|---:|
| period_start | 17.73 | 10.20 | 17.16 |
| dead_ball_inbound | 15.52 | 9.96 | 13.41 |
| after_make | 16.74 | 15.35 | 15.45 |
| after_dreb | 12.91 | 12.33 | 12.40 |
| after_turnover | 10.75 | 10.43 | 10.49 |
| after_ft | 15.50 | 14.45 | 14.51 |

Opening-period duration is now close; dead-ball restart duration improves substantially but remains short. The frequent post-make category barely changes and remains about **1.30s short**. DREB and turnover *samplers* are unchanged; their realized full-possession means can move because outcome mix, foul/OREB continuations, remaining clock and on-court states change. Direct same-input tests verify identical samples for these untouched origins.

## Implementation and temporal controls

- Separate action origin codes identify period starts and team-rebound/dead-ball restarts, replacing their shared generic `other` timing path only when the opt-in restart flag is supplied.
- Three empirical profiles use restart-to-first-action intervals: period start, dead-ball restart proxy, and post-make. They do **not** reuse whole-possession elapsed time as a first-action delay, which would count later foul/rebound continuation twice.
- Fit each target using only source rows dated strictly earlier than that target. Use boundary-usable rows; ambiguous control rows are excluded. The evaluation remains the frozen 145-game slice. No pooled 145-game target mean, constant 1.02-second padding, or target-day events are used to force a fit.
- Retain only positive first-action intervals below 24 seconds in the legal-action profile. The incumbent conditional-on-shot-clock-support sampler still applies. This restriction, source clock/control distinctions and continuation/outcome mix mean the fitted action profile does not directly guarantee a full-possession target duration.
- If no earlier restart profile exists, use the prior-date post-make profile, then the incumbent gamma fallback. One evaluated game has no earlier period-start history (401902644); it is retained and flagged.
- Shot-clock violation probability, foul/rebound probabilities, efficiency scales and original player shooting inputs stay fixed. No fantasy-point rescaling is used.
- The first five clean games completed the smoke test before the full four-shard replay. All 145 games complete with no failures; maximum possession-clock partition error is **3.64e-12 seconds**. Per-game checkpoints preserve completed games and reject a mismatched scope. A finished-checkpoint test proves completed games are not resimulated.

## Validation and limitations

The broad suite ran **408 tests with one skip and no failures**. After adding the checkpoint-scope guard and its regression, **22 focused tests pass**, covering timing cutoffs/fallbacks, input immutability, untouched timer samples, source possession boundaries, integrated ledgers and checkpoint recovery. Production imports and defaults remain unchanged; draft PR #77 is not promoted.

The 145-game set has unambiguous boundaries under the existing reader, not independently certified official possessions. Three one-turnover feed/box discrepancies and all previously documented special-FT/control approximations remain unchanged. Dead-ball inbound is a restart proxy rather than a verified touch timestamp. The 81 flagged games are not silently moved into the primary slice. This conditional development replay is not a pregame forecast/held-out accuracy claim.

## Decision

Do **not** proceed to the late-clock penalty or minutes/role upgrades yet. Isolate the remaining high-volume post-make action/continuation timing and legal-support assumptions first. A first-action profile alone does not resolve the full-possession calibration conflict. Keep possessions (~202.2) and ORtg (~112.5) as simultaneous diagnostics; do not lower efficiency just to conceal the remaining pace excess.

## Reproduction

```
PYTHONPATH=.:tests python scripts/replay_nba_possession_reconciliation.py REPO EVIDENCE SMOKE_OUT 5 0/1 yes
PYTHONPATH=.:tests python scripts/replay_nba_possession_reconciliation.py REPO EVIDENCE SHARD_OUT 0 0/4 yes
# Repeat shards 1/4, 2/4, 3/4 with separate checkpoint directories.
PYTHONPATH=.:scripts python scripts/summarize_nba_restart_timing.py WORKSPACE
```

Use the prior frozen nba-possession-results source traces/summary in the sibling workspace, and sibling nba-restart-shard-0 through -3 output directories. Restart fits are rebuilt from hash-verified source games with strict prior-date cutoffs. These are scoped offline research scripts.
