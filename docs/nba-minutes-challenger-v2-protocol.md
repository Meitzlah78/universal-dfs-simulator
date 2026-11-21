# Offline NBA minutes challenger v2 protocol

Status: prospective protocol only; no v2 fit or production promotion.

## Data inventory
Downloaded 146 archived October 2026 games across 26 dates (October 3–31).
82 are dated October 20–31; 64 precede October 20.
These are date buckets, not verified season-type labels.
Stored archive fields are event_id, date, source, home_score, away_score, events, boxscore.
Season type is absent. Obtain and validate official schedule season-type metadata before admitting October games as regular-season training data.
No missing player box record becomes DNP; only explicit didNotPlay is a verified zero.
Rounded box minutes and overtime remain limitations.

## V1 frozen reference
Baseline: mean of up to five prior observed player/team games.
Residual ridge alpha=10, train-standardized features, unpenalized intercept, final predictions clipped 0–48.
Features: previous observed minutes; exponentially weighted prior minutes (decay 0.7); previous minutes minus rolling mean; prior starter share; days since last observed player game capped at 14; prior minute standard deviation; prior explicit DNP share.
All features use strictly earlier dates, with same-day updates deferred.
No current-game starter flag, DNP label, injuries, Vegas or verified team-rest input.
Prior DNP share already existed in v1, so v2 participation modeling must be evaluated as a changed mechanism, not a newly available signal.

V1 heldout >10-minute absolute misses: baseline 144, challenger 142.
Non-DNP holdout MAE: baseline 5.1941, challenger 5.0459 (hindsight diagnostic only).
DNP holdout MAE worsened to 10.2016 from 8.7899.

## Frozen v2 split
Training: verified regular-season October dates through November 10, 2026.
Validation/development: November 11–19, already examined and not a pristine test.
November 20–21: excluded from final test because already observed or discussed.
Reserved final test: November 22–December 1, 2026. Do not inspect target outcomes to choose features or hyperparameters.
Freeze code/model artifacts and selection criteria before this test begins. If not frozen in time, move the reserved window forward before examining its outcomes.
Require matched cohorts and recompute baseline metrics separately on each partition.
No claim that the earlier overall 5.54 MAE is a holdout threshold.

## Candidate restrictions
Compare rolling baseline, fixed v1, and a two-part participation/conditional-minutes candidate on validation only.
Pregame injury information may enter only with verified timestamps preceding tipoff.
Participation uses earlier explicit DNP patterns; missing roster observations remain missing.
Longer role summaries require actual coverage; October expansion does not guarantee ten regular-season observations per player.
Days since last observed appearance must not be described as verified back-to-back/rest.
Role-expansion labels use prediction minus prior baseline, not actual target minutes.
Report MAE, RMSE, bias, coverage, and starter/bench/DNP diagnostic slices; overlapping slices are not additive error shares.
No live integration until a reserved-test win and later saved-provider shadow comparison.
