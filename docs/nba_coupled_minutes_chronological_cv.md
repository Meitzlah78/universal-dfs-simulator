# Coupled minutes chronological development CV — 2026-11-14

**Decision: no promotion.** Production, settings and PR #77 remain untouched. No parameter changes were made after evaluating the held-out dates. This branch contains offline research only.

## Protocol
All 12 builds/39 physical games inform the chronological study. Remove two actual OT games from regulation-minute scoring. October30's two builds/eight physical games supply the initial training fold; test the ten later builds on five dates (Nov6,7,10,11,13), 29 games. Each fold trains on strictly earlier dates. Both sites and both teams of a game remain on the same side of the cutoff. Training uses all eligible matched player observations, not only the136 downward misses. Latest pretip team snapshots remove duplicate site weighting in fitting and primary minute/pair analysis.

Fit pooled script probabilities with Dirichlet half-count smoothing, matched-player transfer medians including zeros, and minute-tier foul-threshold probabilities/cuts. These are low-dimensional pooled estimates, not reliable team-specific learned tendencies. Retrospective margins and foul thresholds label training data only; no actual evaluation-game labels enter the sampler. Shared game-script uniforms link both teams. Transfers conserve240 team minutes and respect0–48 bounds; unavailable recipient capacity is explicit. A floating-point-only boundary repair makes the kernel acceptable to the strict rotation scheduler. This remains a trial-total foul proxy, not a time-resolved sixth-foul engine.

Independent and coupled full-engine arms each receive fresh pregame event calibration (1024 construction draws seed83) and2000 evaluation draws seed2100. Variable and wider minutes are enabled in both arms. No archived fantasy quantile scaling. Twenty arm/build replays completed with no failures. The shared-only arm is compared in the minute/pair replay, not additionally replayed through full-game fantasy scoring.

## Fantasy interval results
Coverage of80% intervals among actual >5-minute projection misses:

| Tier | DK independent | DK coupled | FD independent | FD coupled |
|---|---:|---:|---:|---:|
| Bench <18 |56.0%|44.0%|55.9%|46.2%|
| Rotation18–27 |47.0%|47.0%|50.0%|54.2%|
| Core28+ |47.3%|50.9%|43.5%|44.9%|
| All players, all minute-error sizes |73.0%|72.0%|72.7%|71.9%|

These are newly paired same-engine controls on the chronological evaluation subset, so they should not be subtracted from the original eight-build historical percentages.1215 matched player forecasts,10 builds,29 unique physical games. DK has27 observed games; FD29. Primary physical-snapshot fantasy coverage73.93%→73.13%; game-weighted change−0.73 percentage points, conditional game-bootstrap95% interval−1.99 to+0.80pp. Bench miss-slice game-weighted regressions have intervals below zero on both sites (DK−16.8 to−5.1pp; FD−21.1 to−4.5pp). Core gains are small and do not establish a robust improvement.

Player-mean projection MAE DK0.258→0.228FP; FD0.242→0.238FP. Maximum team mean residual1.593 real points in both arms across all62 game/build reports, so not every team meets a hypothetical±1-point gate. This was not newly loosened or treated as passing.

## Minute dependence results
Chronological test subset:295 primary bench pairs. Observed dual+5-minute co-spikes10.17%, compared with9.58% in the broader previous development set. Predictions: independent3.71%, shared-only15.25%, coupled4.56%. Coupled Brier0.13231 versus independent0.13537 (game-weighted); conditional95% delta interval−0.00589 to−0.00074. It improves that error metric slightly while remaining substantially undercalibrated on co-spike frequency. Shared-only Brier0.12260, despite overpredicting the mean rate.

Overall minute80% coverage stays74.72% independent and coupled; minute MAE5.132→5.051. Coupled core large-miss minute coverage23.2%→27.5%, bench50.5%→49.5%, rotation32.4%→32.4%. Minute coverage is not fantasy coverage.

## Interpretation and limits
The simultaneous objective fails: modest core/downside improvements accompany harmful bench fantasy-coverage regression and insufficient co-spikes. Do not promote or select amplitudes to hit9.6% on these games. Probabilities/magnitudes and per-fold cutoffs are recorded in folds.json; protocol and row outputs accompany the report.

Dates have been reused in development; chronological CV prevents same-game label leakage but cannot turn these into untouched external holdouts. Bootstrap intervals cluster by physical game, condition on fitted folds, and do not incorporate training uncertainty or multiple endpoint selection. Only five test dates exist. Transfer sizes use matched-player team aggregates, not verified complete substitution stints or causal foul effects. No new causality claim, generic rate widening, candidate regeneration or portfolio optimization follows from this experiment.

The next distinct modeling hypothesis should address receiving-player distribution and minute-centering/availability states, then freeze before fresh chronological validation. Reuse of this set can diagnose development failures, not certify production readiness.

27 targeted tests passed, including game-level probability denominators, all-row fitting, deterministic conservation, scheduler boundaries, heldout-label isolation and prior sampler checks.
