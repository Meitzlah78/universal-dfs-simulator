# Week 6 NFL fallback-rate calibration audit

Offline exploratory temporal holdout. No live app parameter, projection, frozen market trial or DvP trial was modified.

Input repository commit: `35b689b40f02faacf7040a8e8fb2b0f85ab2301d`.
Both compressed archive bytes were checked against their Git blob SHAs before loading.
Week 5: 2,687 rows / 15 games. Week 6: 2,538 rows / 14 games. No duplicate game/play keys; regulation-end markers present for every archived game. This does not independently establish official final status or full schedule coverage.

Fit Week 5 counts with a fixed 1,000-exposure prior centered on the engine's default fallback probabilities; evaluate on Week 6 regulation plays. Exclude conversions, overtime, kneels and spikes. No Week 6 outcome enters fitted probabilities, but the protocol was created after those outcomes, so it is not a prospective trial.

| Metric | Live fallback baseline | Week 5 fitted | Week 6 observed | Change in Week 6 mean log loss |
|---|---:|---:|---:|---:|
| Early-down pass share | 58.00% | 58.07% | 61.11% | -0.000086 |
| Sack share of recorded pass plays | 6.50% | 6.90% | 6.61% | +0.000056 |
| INT given no sack | 2.10% | 1.92% | 1.99% | -0.000013 |
| Completion given no sack/INT | 64.00% | 64.87% | 63.68% | +0.000285 |

Negative log-loss change is better. Two improve and two worsen; do not promote these fitted defaults. Improvements are small and this does not establish player projection accuracy, tail calibration, field realism or portfolio ROI. The baseline is a fallback-rate diagnostic, not a replay of the full live engine's player-history, score-margin, market and weather adjustments.

Week 6 regulation yards per completion: 10.676 (626 recorded completions); yards per recorded rush: 4.000 (678 runs). These are observations, not recommended new constants. Scrambles are recorded runs; event denominators are stated explicitly in the script.

The archived schema lacks fumble-loss, kick-result and complete scoring fields. Do not reconstruct exact DK/FD actuals from this reduced archive or fill unknown events with zero. Full weekly player stats and verified DST fantasy scores are needed for exact player-level scoring; DST must not be inferred from weekly offensive records.

Reproduce from repo root:

```sh
python scripts/calibrate_nfl_archive.py --train data/pbp/2026_week_05.csv.gz --test data/pbp/2026_week_06.csv.gz --output /tmp/week6-rate-calibration.json
python -m unittest discover -s tests -p test_nfl_archive_calibration.py -v
```

The JSON report includes archive SHA-256 hashes, game audits, denominators and limitations.
