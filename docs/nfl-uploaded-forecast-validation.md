# Uploaded NFL forecast validation — 2026-11-03

Ran the frozen forecast audit on 615 matched player/platform/date observations. Fit a fixed per-platform additive bias correction using the 557 Nov 1 pairs only, with a zero-bias prior weight of 20, and evaluated 58 Nov 2 pairs. This is a retrospective, exploratory test, not a preregistered prospective holdout. No hyperparameters were selected from the Monday results.

| Platform | Monday projection MAE | Candidate MAE | Projection RMSE | Candidate RMSE | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| DraftKings | 2.3910 | 2.3680 | 3.3353 | 3.3402 | MAE slightly better, RMSE worse |
| FanDuel | 2.2300 | 2.2447 | 3.1644 | 3.1645 | Both worse |

No correction is activated. Fitting the same date and reporting its fit error as validation is prohibited. Tests verify that changing the later actuals cannot change fitted parameters, and that duplicates/missing actuals are rejected.

The two original Monday bundles also retain 10,000 shared player draws for 29 matched players per platform. Direct distribution checks give mean player CRPS 1.6754 DK / 1.5759 FD; central 80% intervals cover 28/29 DK and 27/29 FD players. Joint energy and variogram scores are retained in the JSON report. These describe one CHI/SEA outcome; they do not establish calibrated coverage or correlations. DK and FD contexts are not independent games. The direct DK simulation-mean MAE is 2.3799; the imported scalar comparison rows omitted that mean, so it is scored from the immutable NPZ rather than filled with zero.

Existing component report 7467fb1aa0606829 already tested 93 earlier training games, 14 selection games and 14 final games through Nov 2. No new component passed. The prior accepted rushing-distribution version d6464a5c58186cc1 remains active. That consumed final block is not repeatedly reused to search for a passing model.

Full-game role, volume, variance and dependence promotion still requires complete frozen replay inputs and explicit final raw stats, at least 20 independent validation games, and the existing per-stat/joint gates. Fantasy points are not inverted into raw stats. This audit neither bypasses those gates nor claims all player-performance learning is finished.

Reproduce the scalar forecast audit:

```sh
python scripts/validate_nfl_uploaded_forecasts.py --data-root data --output /tmp/nfl-uploaded-forecast-validation.json
python -m unittest discover -s tests -p test_uploaded_forecast_validation.py
```

The aggregate report at `data/nfl_validation/reports/2026-11-03-uploaded-forecast-validation.json` also retains the additional immutable-bundle distribution check and existing component status at the audited commit. Raw contestant identities are not included.
