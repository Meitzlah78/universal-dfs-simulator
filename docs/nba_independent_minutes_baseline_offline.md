# Independent pregame minutes baseline — 2026-11-14

**Result: runs without provider projection features, but does not beat saved provider minutes. No promotion. Production and PR #77 remain untouched.** This is a first history-only point-forecast benchmark, not an autonomous fantasy-point projection pipeline.

## Frozen baseline
The estimator receives only player name, team and archived injury availability. Provider minutes, fantasy points, salaries, ownership, starter labels and provider-defined tiers never enter prediction. No provider-positive rotation filter is used to choose the independent roster. OUT/O/IR/INACTIVE/SUSPENDED are excluded; other statuses remain candidates, including unresolved questionable/doubtful players. Saved availability is not assumed to be a confirmed active list.

For each candidate, average the last five explicit prior-game minute observations with a three-observation exponential half-life. Include explicit DNP zeros; do not invent zeros for absent records. Cold starts use the earlier league roster-observation mean and are tagged. No parameter sweep or post-result changes to this estimator. Allocate its own weights to240 minutes with a48-minute cap. Fewer than five positive-support candidates is an explicit error, never an invented rotation. All144 team/site snapshots completed and conserved240 minutes.

Historical features require game date strictly before forecast game date AND verified historical completion timestamp before the archived capture. Same-day games are excluded. Historical games with OT or missing final regulation boundary are excluded.219 historical games supply candidate observations in the source inventory; each individual forecast sees only its permitted earlier subset. Historical ESPN boxscore MIN is rounded whole minutes. Early-October history is present and recovered source metadata does not certify regular-season-only coverage.

Primary model uses rolling earlier-game history, mirroring pregame inference. A separate fixed-history sensitivity excludes all games on/afterNov6 from features, so the29 previously examined verification games cannot update that arm. For older forecast dates both arms still enforce their own earlier-date cutoff. These are retrospective development checks, not pristine external holdouts or claimed production validation.

## Matched accuracy
12 builds,37 unique non-OT games.1875 matched site-specific candidate forecasts; latest pretip team snapshots deduplicate to961 physical player forecasts.793 of these belong to the earlier positive-projection audit cohort. No team forecast failures.

| Original audited cohort | Saved provider minutes MAE | Independent rolling MAE | Fixed pre-Nov6-history MAE |
|---|---:|---:|---:|
| DK,750 forecasts |4.884|5.283|5.638|
| FD,793 forecasts |5.042|5.352|5.731|
| Primary deduplicated,793 |5.026|5.369|5.748|

MAE is minutes, lower is better. Provider labels are almost entirely RotoWire (1874 rows; one same-game DraftKings-feed minutes row). Comparator uses the saved raw input minutes, not normalized physical simulator means. Provider tiers are used for diagnostics only, never as features.

Across all961 common available rows, including explicit provider-zero forecasts: provider MAE4.784 versus independent5.128; >5-minute misses34.5% versus43.0%. Provider aggregate bias−0.066 versus independent−0.886 minutes (predicted minus actual). A near-zero aggregate provider bias does not rule out role-specific errors, but the data do not support assuming a universal provider overprojection. Primary game-weighted independent-minus-provider MAE delta+0.342 minutes; descriptive95% game-cluster bootstrap interval−0.058 to+0.766. No credible accuracy improvement is established.

## Roster and scoring gaps
There are2134 available-roster forecasts across the144 team/site snapshots. Fourteen are tagged cold starts; only one cold start is in the matched primary scoring cohort.259 candidate forecasts lack an explicit actual-minute record and are retained in unmatched_forecasts.csv. They are not marked zero or DNP. The independent baseline allocates an average11.65 team minutes per snapshot to candidates outside the common scored cohort (median10.04, maximum59.21). This is unscored prediction mass, not proof those minutes were played or wasted. Seven team/site snapshots also contain an observed playing athlete outside the saved available roster. A complete active-roster reconstruction is therefore still needed before claiming whole-team forecast accuracy.

Do not repair this retrospectively by filtering independent candidates with provider minutes>0 or future participation. Such a shortcut would defeat the independent forecast test. Any stronger roster eligibility inputs must be independently point-in-time verified.

## Decision and next boundary
The baseline establishes a reproducible independent minutes forecast and an honest provider comparison. It is not good enough to replace provider inputs. Recent minutes alone do not capture current availability, return-from-injury roles, team changes, rotation decisions or context reliably; this benchmark does not identify their causal contributions. No fantasy-point forecast, interval coverage or new portfolio performance is claimed. A separate independent points model and frozen side-by-side benchmark remain unfinished.

42 targeted tests pass, including the previous36 and no-provider-dependence, same-day/future completion exclusion, cold-start handling, OUT removal,240-minute feasibility and fixed-history cutoff checks. Research code is on codex/nba-shared-bench-offline only.
