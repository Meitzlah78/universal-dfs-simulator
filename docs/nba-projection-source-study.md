# Prospective RotoWire / Lineups projection comparison

This study observes both sources without changing Simmah's projections, minutes,
field generator, or solver. It is independent of the RotoWire-only source PR.

Before games, run:

```sh
python scripts/track_nba_projections.py capture --directory /path/to/study
```

On later days, keep those exact snapshots and run:

```sh
python scripts/track_nba_projections.py grade --directory /path/to/study
```

The capture reads the public Lineups page's structured data and each site's
dedicated RotoWire projection response, not uploaded overrides or app blends.
It records both point forecasts, both minute forecasts, retrieval times, source
IDs, raw-response hashes, and coverage. FD and DK fields stay separate. The
RotoWire main slate is selected by exact date, format, largest game count and a
unique default tie-break; ambiguous slates are rejected. Only same-day unstarted
games with valid RotoWire clocks are frozen. Source observations older than 30
minutes are rejected. A failed fetch creates no usable forecast.

Lineups does not expose a forecast date/as-of timestamp in its page data. Its
records are associated by unique name, team and opponent with the same-day dated
RotoWire games observed at retrieval. This is **not** an ID-verified source-date
join; the qualification is retained in every snapshot and report. Opponent/name
mismatches, missing projections and ambiguous matches remain missing, never zero.

The grader scores ESPN FINAL box scores with the shared FD/DK scoring functions,
including DK bonuses. Only explicit final DNPs can yield a zero without statistics.
It chooses the last frozen pretip observation per player/game/site, preventing
reruns and repeated snapshots from overweighting players. It reports paired MAE,
RMSE, signed bias and coverage on exactly the same final matched players for both
sources. Zero and negative actual fantasy points are valid; missing actuals and
live games remain unmatched. Stat corrections can change final results.

No historical forecasts are reconstructed after games. The supplied October 23
contest cannot establish predictive accuracy without genuine pregame snapshots.
Keep at least several distinct slate dates before deciding to replace a source.
Archive the study directory after every run; a local directory alone is not a
persistent collection service. A scheduled assistant can restore the most recent
archive, capture fresh inputs, grade previous captures and save the updated archive.
