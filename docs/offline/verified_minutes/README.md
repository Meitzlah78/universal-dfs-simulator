# Verified-input minutes prototype — offline only

No live imports, default changes, or PR #77 edits. This is implementation groundwork, not an accuracy improvement claim.

## Recovered evidence

All 219 history games were matched by event ID and normalized team pair to ESPN per-event season metadata: 60 preseason, 159 regular season. Source URLs and retrieval times are recorded in season_metadata.json. The league scoreboard header is unsafe for historical classification: on 2026-10-14 it describes regular season while individual games explicitly describe preseason. No calendar-based season inference is used. These descriptive season labels are recovered retrospectively; they are not historical injury/eligibility evidence.

## Experimental path

`forecast_verified_team` requires dated, sourced eligibility and role priors. Unknown eligibility stops this arm rather than removing the player or assigning zero. Explicit ineligible evidence excludes a player. Evidence publication must precede capture and its validity interval must include capture.

Historical rows require verified season metadata and positive played observations or confirmed DNPs. Missing participants and numeric zero without confirmed DNP are not absences. Regular-season experiments exclude verified preseason records. Source season slug `regular-season` must be explicitly mapped to internal `regular` during ingestion; missing/unrecognized labels cannot be silently mapped.

Historical influence uses absolute decayed evidence mass, not merely a normalized recency average. A stale estimate approaches its current independently learned role prior. Prototype half-life 14 days / prior strength 3 are experimental fixed values, not fitted or promoted defaults.

Role-bound fitting uses earlier verified pregame role-labelled records only (minimum 20 samples). Fifth/95th-percentile bounds are forecast constraints, not physical basketball limits. Weighted constrained redistribution preserves 240 team minutes and adjusts uncertain roles more. No universal 38-minute ceiling. An infeasible bound set is reported with no automatic relaxation.

## Remaining checkpoint

The old benchmark stripped participation flags, season metadata and pregame role provenance. Season recovery is complete, but retrospective roster membership alone does not prove historical game eligibility. The official dated NBA lineup feed is reachable and contains rosterStatus and timestamps, but timestamp timezone and Active semantics require verification before they can certify historical eligibility. An archived Active candidate or omitted boxscore row is insufficient.

No combined historical accuracy result is reported yet: dated eligibility/current-role priors and sufficiently supported earlier role distributions must first pass the input contract. Retain original cohorts and report unsupported snapshots separately; do not achieve apparent gains by dropping them. Then compare unchanged baseline, season filter, age shrinkage, bounded allocation and combined arms chronologically. No provider minutes as features, no test outcomes in role bounds, no promotion without fresh validation.
