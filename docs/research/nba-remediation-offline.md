# NBA remediation: offline foundations

This branch repairs research tooling and adds isolated mechanics/policy challengers. It does not change the live NBA engine, UI selection policy, provider role precedence, or production parameters.

## Implemented

- Separate ESPN rotation reconstruction from the newer NBA CDN parser. Preserve explicit unresolved periods rather than guessing starters. Both research callers use the correct format. Validate complete period coverage and monotonic clocks.
- Update the ownership-upload UI regression to the current two-provider label.
- Add a saved-build selector ablation with source-hash verification. Hold candidates and pregame scores fixed; compare diversity/caps independently. Also exercise the existing 5% budget selector offline, preserving explicit infeasibility and certification-timeout outcomes.
- Add research primitives for conserved stochastic named-player minutes, personal fouls, six-foul disqualification, foul-trouble and optional score-aware blowout priorities, player-specific shooting splits, one/two/three-shot FT handling, and possession/period/24/14-second clocks.
- Couple minutes and foul state in a regulation-only six-second-grid integration harness. Source provisional foul intensities strictly from saved PBP box scores before November 6, 2026. This is not a complete scoring/possession or overtime simulation.
- Add an offline stale-provider blend policy. Unknown freshness and fresh provider roles remain intact; only dated stale rows may blend approved archive components. Future provider timestamps are rejected. No source fantasy projections or minute targets change.

## Measured selector result

On the six previously uncapped builds, diversity 25 reproduces saved selection quality. Diversity zero increases summed pregame Top-1% scores by 32.2–85.4%; removing automatic caps alone has no effect. This isolates the diversity objective rather than correlation generation or stacking rules.

A three-second-per-stage 5% budget experiment succeeds on all six uncapped portfolios. Actual loss versus certified feasible quality optimum is 0–4.98%. Two second-stage searches retain the optimum after timing out; uncapped concentration can reach 100%. No cap was relaxed. Historical Nov 6 capped cases are not comparable to current policy: DK is infeasible under current limits; FD's optimum is not certified within three seconds. These are development results, not profit or promotion evidence.

## Limits and next integration

The broad six-foul rule has a rare exhausted-roster exception under NBA Rule 3. The research harness deliberately reports fewer than five eligible players as unsupported; it does not implement that exception or silently reuse a disqualified player. Other complex shot-clock reset/shot-in-flight rules remain outside the primitive. Independent Poisson foul timing and deficit-based coaching priorities are hypotheses, not trained NBA behavior.

No coverage improvement is claimed. Minutes standard deviations in the harness are assumptions; the archive lacks explicit competition labels. Full-game event/clock/rotation integration, component fitting, point-in-time minutes residual training, independent calibration validation and fresh selector holdouts remain necessary before promotion. The original eight slates are development cases only.

Official references:
- https://official.nba.com/rule-no-3-players-substitutes-and-coaches/
- https://official.nba.com/rule-no-7-24-second-clock/
- https://official.nba.com/rule-no-9-free-throws-and-penalties/

Reproduce tests with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=.:tests python -m unittest discover -s tests -p 'test_nba*.py'` and `python scripts/check_nba_build.py`.

## Integrated replay result — candidate rejected for promotion

The subsequent offline full-game kernel connects fixed supplied rotations and stochastic minutes to disqualification/foul-trouble/blowout replacements, player-specific shot probabilities, mixed FT trips, quarter-bonus approximation and a 24/14-second possession clock. Team make-rate calibration scales player probabilities relative to the unchanged pooled model. This remains a research arm; production imports are untouched.

The frozen 227-game corpus is pinned to the original audit IDs and hashes. A dedicated 128-draw conditional replay completes 226 games. One game (`401909909`, ATL–IND, November 2) reaches unsupported eligible-roster exhaustion: only six IND players have positive observed minutes in the conditional input. Unused/possibly inactive bench players are not invented as replacements.

| Conditional completed-game mean | Actual | Baseline | Challenger |
|---|---:|---:|---:|
| Total points | 227.35 | 235.22 | 213.84 |
| Player field-goal attempts | 175.48 | 177.49 | 155.16 |
| Free-throw attempts | 52.00 | 45.43 | 51.82 |
| Possessions proxy per team | 102.65 | 100.46 | 101.90 |

Possessions are the approximate box-score formula `(FGA + .44 FTA - OREB + TO)/2`; shot-clock violations count as challenger team turnovers. This is not reconstructed exact pace. Improved proxy agreement does not cancel the large FGA and scoring shortfall. Team-heave and source accounting differences also limit FGA comparison.

Game-level FTA P10–P90 coverage improves from 56.6% to 69.9%. In the observed 30-plus-minute cohort (995 player-games), actual FD scores exceed conditional P90 in 13.5% baseline versus 24.7% challenger; P95 exceedance is 7.2% versus 16.1%. Those ceilings worsen alongside scoring underprediction. Both arms receive observed rosters/minutes, so these are conditional diagnostics, not pregame validation.

A separate eight-build forecast replay preserves all 1,008 previously graded observations and uses pre-date priors, saved player/market inputs, 128-draw parameter preparation and 512 independent evaluation draws. The original baseline has 10,000 evaluation draws. DK coverage moves 68.6% to 67.3%; FD 65.6% to 64.7%; the >5-minute-miss slice moves 42.2% to 39.0%. Mean interval widths do not widen materially. Four dates and shared games do not support a significance claim. All 49 calibrated game-site replays pass the existing four-point market guard, yet forecast coverage fails to improve. No unresolved forecast overtime trials remain.

Stale-provider policy updates remain zero across eight builds (1,447 provider-role rows have unknown freshness). Do not fabricate freshness or overwrite the provider just to trigger archive use.

The descriptive diversity sweep (0/5/10/15/25/50) is logged on eight development builds; no new default is selected. For six uncapped cases, diversity 5 loses 1.06% mean / 2.14% worst summed quality versus diversity zero, but still permits 100% player exposure in one case. Independent lineup uniqueness does not guarantee healthy exposure concentration.

Current checkpoint: **not promotion-ready**. FTA means improve, but scoring, FGA volume and ceiling/interval calibration do not pass. Next modeling work should isolate foul-event clock consumption, shot-clock expirations, rotation/mean interactions and minutes residual modeling before changing selector defaults. Role blending requires usable provider freshness metadata and temporal component validation.

Reproduce the two distinct arms:

```
python scripts/replay_nba_full_game_offline.py REPO EVIDENCE OUTPUT
python scripts/replay_nba_conditional_distributions.py REPO EVIDENCE OUTPUT
python scripts/sweep_nba_diversity_offline.py EVIDENCE SWEEP.json
```

Baseline instrumentation is isolated in `simmah_nba_baseline_audit_offline.py`; tests verify identical scores, stats, team points and elapsed time to the unchanged live baseline at a fixed seed. Added cutoff and integrated ledger tests pass; broad NBA discovery runs 389 tests with one skip.
