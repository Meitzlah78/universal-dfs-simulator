# Independent minutes: injury, recency and context — 2026-11-14

**No promotion.** Injury-associated error is the largest measured gap. The standalone feature upgrades do not beat provider minutes. A small ensemble gain remains uncertain. Production and PR #77 are untouched; independent fantasy-point forecasting remains gated.

## Important baseline correction
The original baseline already used the last five explicit earlier observations with exponential half-life three games. It was not an equal-weight/full-season model. Its default predictions are unchanged by this work (maximum numerical difference3.6e-15 minutes). Optional recency settings were added to the offline estimator only.

## Pregame injury slices:37-game descriptive set
Latest pretip team snapshots remove duplicate DK/FD weighting. Classify a historical-core vacancy when an archived OUT/O/IR/INACTIVE/SUSPENDED player averaged>=28 minutes over their last five earlier positive-minute observations. No provider minutes or starter designation enters this feature. This is a core-role proxy, not proof the athlete was a current starter. No detected vacancy is NOT confirmed full strength: missing prior roles and unresolved Q/D remain explicit.

793 primary audited player forecasts:

| Pregame team context | Forecasts | Provider MAE | Independent MAE | Gap |
|---|---:|---:|---:|---:|
| Historical core OUT |244|4.73|5.55|+0.82|
| No detected core vacancy |549|5.16|5.29|+0.13|

The injury-associated rows are31% of observations and account for roughly74% of the aggregate absolute-error gap. This is descriptive association, not causal identification of injuries or commercial news inputs. Team-level strata overlap physical games when opposite teams have different vacancy states.

| Provider-defined diagnostic tier | Forecasts | Provider MAE | Independent MAE |
|---|---:|---:|---:|
| Core28+ |290|4.20|4.66|
| Rotation18–27 |271|4.93|5.30|
| Bench<18 |232|6.17|6.34|

Provider tiers are evaluation labels only. Independent forecast tiers are also retained in row outputs for audit. Among injury-associated rows,82 reflect a core OUT athlete who played the last observed team game;153 lack enough explicit recent participation records to distinguish a new vacancy from an already-absorbed absence; nine reflect previously absent cores. Those tiny/sparse subgroups cannot establish causation.

## Chronological development checks
October30 supplies initial training (eight games). The five later dates supply29 evaluation games,747 primary common available forecasts or629 in the original audited positive-projection cohort. Models/selectors fit only earlier dates; no same-game opposite-site training. Rolling historical inputs require earlier game dates and completion before capture. Recipient patterns use only earlier reconstructed single exits from the116 accepted pre-Nov6 games, with completion verified before the current snapshot. No future/same-game PBP enters features.

Candidate families:
- Recency: original last5/half-life3; last3/half-life1; last observation; effectively uniform last5. Select by earlier physical-game-weighted MAE.
- Vacancy: route each known core-OUT role estimate to at most two supported active recipients; make zero-sum proposals and test fractions0,.25,.5,1. Select fraction from earlier data. Unsupported donors remain logged; no invented recipient.
- Context: fixed ridge penalty10 on earlier residuals, using own-minute scale, completed-game back-to-back calendar (including OT games), archived absolute spread, vacancy and recipient weights. Same features are applied to all available players, then bounded and allocated to240. No provider projection feature.
- Ensemble: learn independent weights0,.25,.5,.75,1 from earlier dates. This is explicitly provider-assisted, not a standalone independent forecast.

MAE on the629 audited chronological forecasts:

| Arm | MAE minutes |
|---|---:|
| Saved provider |5.12|
| Original independent |5.49|
| Fixed faster recency |5.40|
| Last game only |5.81|
| Uniform last5 |5.66|
| Earlier-date-selected recency |5.49|
| Earlier-date-selected vacancy |5.49|
| Learned rest/spread/vacancy context |5.57|
| Raw point-forecast blend |5.03|

Earlier-date selection chose the original recency arm and vacancy fraction0 in every fold; do not override those choices using evaluation outcomes. Faster recency improves bench MAE6.58→6.12 but worsens core4.77→5.01 on this development set. Context performance does not imply rest/spread are useless; only18/144 team/site snapshots are back-to-backs, and the feature/model/sample is limited.

## Budget-correct ensemble sensitivity
Raw point-forecast blends need not sum to240 because saved provider totals can differ or have missing values. After observing the raw blend result, a methodological sensitivity normalized BOTH the provider-only control and the blend to240. It is explicitly a development diagnostic, not new preregistered holdout evidence. The same earlier-date weight-selection grid is used; no evaluation-date tuning.

Six team/site snapshots lack complete provider minutes and are marked unsupported for this comparison, not zero-filled. On the600 complete-input audited forecasts spanning29 games, normalized provider MAE5.149 versus normalized blend5.060. Game-weighted delta−0.063 minutes, conditional95% game-cluster bootstrap interval−0.217 to+0.082. Thus additive value is plausible but not statistically credible. Selected independent weights are25%,25%,25%,50%,25% across the five test dates. Every supported normalized blend supplies240 minutes within0–48 player bounds.

Bootstrap intervals cluster physical games, condition on fitted models and omit training/selection uncertainty and multiple comparisons. These dates have already informed development; they are not a pristine external holdout. The259 missing-actual candidates remain unscored throughout. No interval, co-spike, fantasy-point or contest-return improvement is claimed.

## Data limits and next boundary
Across144 team/site snapshots:45 historical-core vacancy proxies;78 snapshots include an OUT player lacking positive-minute history;57 have unresolved Q/D;18 back-to-backs; no missing archived spread or previous team-game calendar. Missing active-roster/participation records still limit injury adaptation. A current OUT label plus old positive minutes does not distinguish a fresh vacancy from a role change already reflected in recent teammate minutes. That distinction should be addressed with point-in-time roster/availability history rather than automatic28–34 minute promotions.

49 targeted tests pass, preserving all original42 checks and adding weighting-default parity, options/budgets, strict historical role cutoffs, no-provider context features, invalid settings, normalized ensemble conservation and explicit missing-input rejection. None of these experiments is deployed.
