# NBA nightly historical role learning

The 3 AM Eastern PBP archive workflow now runs an automatic historical-role learning stage. It saves its evaluation report even when it rejects an update. Approved immutable versions are loaded by the shared position-prior application path used in both DK/FD builds and simulation late swaps. No approved version means the existing behavior is retained.

## Scope

This learns player per-minute shot, assist, rebound, steal and block rates for players who would otherwise receive pooled position priors. It preserves sourced individual rates, provider point projections, provider minutes, eligibility, ownership and the fixed event-rate model. Player names are normalized and ambiguous names are excluded; ESPN IDs are retained for audit. At least 60 training minutes are required before applying a learned player rate.

This is **not** an automatic fantasy-point projection correction, ownership calibration, minute forecast, portfolio-ranking calibration, or evidence of improved contest ROI. Those require timestamped pregame forecasts and separate outcome validation. Existing pooled event fitting has documented approximations and is not automatically deployed by this workflow.

## Update process

1. Read archived games strictly before the target date; recheck final scores and player observations. Reject malformed records and report them.
2. For the first evaluation, reserve the most recent three complete archived dates. After approval, use only dates later than the last approved validation date. Require at least two validation dates, 30 training games, 10 validation games and 100 held-out player observations.
3. Fit shrunk player rates on earlier dates only. Initial comparator is the fixed position-prior model; subsequent evaluations use the last approved historical-role model with the fixed prior as fallback.
4. Predict held-out stat counts conditional on **actual minutes**. Compare mean absolute error separately by role. Require at least 1% mean normalized improvement, with no role worsening by more than 2%. These are fixed operational gates, not confidence guarantees or a profitability test.
5. Only passing models enter the checksummed version registry. Preserve all previous versions. Never refit a promoted model with its evaluation games.
6. Load only versions activated on or before the selected slate date. Validate training/validation ordering and checksum; corrupt models fail closed.

## Evidence and operation

- `data/nba_models/learning_reports/YYYY-MM-DD.json`: candidate status, rejection reason, per-role error, training and validation game IDs.
- `data/nba_models/learned_roles_index.json`: approved versions and checksums, created after the first passing candidate.
- `data/nba_models/learned_roles/`: approved immutable models.
- The setup view shows the evaluation status and, when applicable, the version and player match count.
- Training runs after archiving even when some downloads failed, using only records that passed validation. Download/learning failures still fail the workflow; saved games and reports are committed before reporting failures.
- Rejected or insufficient-sample candidates do not replace the approved model. To roll back an approved version, remove its registry entry via a reviewed repository change; immutable files remain for reproducibility.

Initial local evaluation: 129 validated archived games, 111 training / 18 validation, 395 held-out player observations. Candidate rejected because steal error worsened by 3.2%, above the fixed 2% limit. No initial model was activated.
