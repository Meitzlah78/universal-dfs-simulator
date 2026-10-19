# DraftEdge DvP prospective trial: WAS at SF, October 19

Frozen before the scheduled October 19 8:15 PM Eastern kickoff. This is a point-projection challenger, not a change to Simmah's live PBP engine, lineup construction, or ownership model.

All 32 defenses were captured for each of QB/RB/WR/TE, with separate DK and FD points allowed. The baseline is the already frozen morning DFF/DraftEdge blend in `data/market_trials/2026-10-19-was-sf/frozen-comparison.csv`. The matchup arm applies a fixed, exploratory 25% shrinkage of the opponent/position league-average FPA ratio, capped at +/-10%. Kicker and DST projections stay unchanged. These constants were declared before outcomes and must not be selected again after viewing results.

The current public rankings cannot establish past predictive performance: they may include the completed games one would be testing. The exact underlying blend weights and as-of cutoff are not exposed. This snapshot can be tested prospectively against tonight's final scores. It is not a historical backtest or a claim of improvement. Existing source projections may already include matchup information, so the experiment directly tests whether adding this adjustment helps or double counts it.

Run after verified final weekly statistics become available:

```bash
python scripts/score_market_trial.py --trial data/dvp_trials/2026-10-19-was-sf/frozen-comparison.csv --weekly /path/to/final-weekly-stats.csv --output /tmp/dvp-results.json
```

Use only verified final records for game `2026_06_WAS_SF`. Missing players are excluded rather than scored zero. DST is excluded unless verified contest actuals are separately available. Report baseline and challenger absolute error on identical matched players, and distinguish the adjusted QB/RB/WR/TE subset from unchanged kickers. One game is insufficient evidence for deployment or ROI claims. The FD baseline retains the earlier caveat that generic DraftEdge projections' scoring basis was not independently confirmed.

`rankings.csv` preserves all 128 source rows. `manifest.json` records fetch timestamps, source URLs, raw-response hashes, kickoff and fixed formula. `frozen-comparison.csv` is immutable pregame input for later grading.
