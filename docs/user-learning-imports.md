# User-provided learning evidence

Standing user instruction (2026-11-02): Import useful completed-contest results, pregame build exports, source projections and optimizer benchmarks supplied in this conversation. Deduplicate sources, preserve provenance, and distinguish active field calibration from validation-only evidence. Future imports still require a tool execution; chat attachments do not directly update the app.

The Nov 1 NFL imports add four anonymous field profiles to `data/field_history_seed.json`, consumed by the existing runtime history loader and matching-format field calibration. They cover 638,180 fully parsed rosters. Empty/null rows are excluded; DK Showdown has 23,579 complete rosters out of 23,781 contest entries. Raw entry IDs, usernames and contestants' individual rosters are not retained in these profiles.

The app's existing NFL score loader reads `data/nfl_results/2026-11-01-uploaded-contests.json`: 799 explicitly published professional-player scores. DK Captain rows are excluded from base-score storage after verifying their 1.5x relationship to FLEX scores. Unlisted scores remain unknown. These are user-asserted final standings, not independently verified raw box scores.

`data/nfl_validation/2026-11-01/` retains 557 matched projection/actual rows and 11 screenshot-transcribed provider lineup benchmarks. The first screenshot pair is RotoWire per the user's correction. DFF and FantasySportsEdge are not treated as independent source votes. Frozen inputs are preserved; no outcome-based reranking is labeled pregame.

`data/nba_validation/2026-10-31/` retains two NBA standings summaries with explicit player scores, roster-derived ownership, duplicate histograms, and the supplied 210-player FanDuel pool. Its pregame capture time is unverified; this is validation evidence, not approved role-training input.

`data/learning_imports/2026-11-02.json` records source and build hashes. The duplicate DK Classic ZIP is explicitly identified and not counted twice. Existing source builds remain available in their original user-controlled storage; this repository stores derived learning/validation data.

No full-game NFL or NBA role model is promoted by this data import. Raw event/stat training and later held-out validation remain required for parameter activation. Standings fantasy points must never be inverted into passing, rushing, receiving, minutes or usage observations.
