# Current-engine FanDuel diagnostic

The saved 271-player FanDuel projection inputs were used to prepare 10,000
independent evaluation outcomes and a separate 10,000 construction outcomes.
Both matrices are finite and distinct. Historical role inputs were not archived,
so this diagnostic explicitly used the model's default roles and neutral
weather. It is not the original app run, a pregame holdout, or a profitability
backtest. Actual contest scores were loaded only after simulation preparation.

The mean absolute projection residual was 0.407 points, with a maximum of 2.512.
Defense mean residual magnitude averaged 1.073 points, larger than offensive
positions. Defenses and kickers remain outside the offensive event-input fitter.
That is a model limitation, not evidence that adding a constant score offset
would preserve valid football outcomes.

Across the forty QB/top-two projected WR-or-TE pairs, generated score
correlations ranged from 0.338 to 0.627. These are simulated relationships, not
estimates of correlation accuracy. Repeated pregame snapshots and completed
slates are needed to assess their calibration.

Among 262 players with posted actual scores, 82.1% landed inside the generated
P10–P90 interval on this slate. Missing actuals were not filled with zero. Players
share game outcomes, and this single observed coverage figure cannot establish
reliable interval calibration. All twenty QB scores were inside their intervals;
more slates are needed to determine whether those QB ranges are too broad.

Reproduce from the repository with:

```bash
python scripts/audit_fd_model.py --players PLAYERS.csv --standings FD_RESULTS.csv --cache-root CACHE_DIRECTORY --output REPORT.json
```

Use `--roles` and `--weather` for frozen pregame JSON inputs when available.
Omitting either explicitly uses defaults, not recovered historical evidence.
The preparation key in the JSON report identifies the input/model snapshot.
Raw outcome caches and contest entries are not committed.
