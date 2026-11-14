# Fresh absences and tier-specific recency — offline, 2026-11-14

**Decision: no promotion.** A tier-specific point forecast improves some errors but still trails the provider, worsens the core tier, and lacks statistically credible overall gains. Earlier-date training selects no fresh-only boost in every fold. Production and PR #77 remain untouched; independent fantasy-point forecasting stays gated.

## Recovery and provenance
The scratch execution state reverted to an older checkpoint. Research code was recovered from commit c5d7ac2ca01ddc80586bb582d00642aed84d21dd on codex/nba-shared-bench-offline. Saved benchmark, context and recipient reports were recovered from their persistent artifacts. All2134 available-roster forecasts across144 team/site snapshots were reconstructed using BOTH1875 scored and259 unscored candidate rows. This does not select the roster based on actual participation. The original independent baseline reproduced to1.1e-14 minutes, establishing unchanged roster membership/normalization. Q/D availability treatment is equivalent to the original estimator; archived core-OUT lists come from the saved pregame context metadata. The259 unknown actual-minute records remain unscored, not DNPs.

## Participation inference
Build an earlier-team-game calendar from231 archived completed games, including OT. Require an observed final period boundary and completion timestamp before the snapshot; same-day games cannot enter history. Positive recorded MIN proves prior participation. An explicit didNotPlay flag with missing/zero MIN proves DNP. Zero rounded MIN without explicit DNP is unknown; an athlete absent from the boxscore is unknown. Missing games/records are never absence-to-zero imputed. These labels identify participation, not the medical reason for a missed game.

For a historical-core player currently marked OUT in saved pregame availability:
- Fresh: played the most recent completed team game, or explicitly DNP last game and played the game before.
- Ongoing: at least three consecutively verified DNPs. No additional boost.
- Two-missed transition: two DNPs followed by a played game; retained separately, no automatic boost.
- Unknown: insufficient/ambiguous records. No automatic boost.

Scan all earlier team games for the verified streak; retain the last three labels/IDs and whether streak length is exact or a lower bound. Prior role>=28 comes from earlier positive-minute observations; no provider forecast or current actual minute tier enters this feature.

47 core-OUT observations across both sites:19 fresh and28 unknown. After site deduplication:24 player-game observations,10 fresh and14 unknown. No three-game ongoing streak is verifiable in this sample. This does NOT establish that long-term injuries were absent; it means the archive cannot verify the proposed ongoing subgroup here. Seventeen team/site snapshots have supported fresh recipient routes; there are no unsupported fresh recipient cases in this run. Immediate replacement evidence does not identify a causal vacancy-minute effect.

## Frozen candidate and chronology
Tier classification uses the original independent raw historical mean before allocation: core>=28, rotation18–27, bench<18. Use last10 observations/half-life5 for core; retain last5/half-life3 for rotation; last3/half-life1 for bench. Include explicit historical DNP observations in the independent minute history; historical OT minute totals remain excluded from the point-estimate windows, while OT participation remains usable for absence classification. Allocate all available players to240 minutes with0–48 bounds. Longer/faster windows are one predeclared hypothesis, not universally optimal role settings.

Fresh-only vacancy proposals use earlier verified single-exit recipient relationships (at most two recipients per OUT player), and only when state=fresh. Unknown/ongoing/transition cases receive no extra proposal. Compare fractions0,.25,.5,1 and select using strictly earlier-date physical-game-average MAE. Evaluate on the same chronological development setup: October30/eight games initially train; five later dates/29 games verify. Both sites of a game stay on the same side of the cutoff. No same-game data enters pregame features. Complete independent vectors conserve240 minutes; no full-game fantasy or contest replay is claimed.

## Paired minute MAE
On629 primary audited forecasts across29 verification games:

| Slice | Provider | Original independent | Tiered + earlier-selected fresh boost |
|---|---:|---:|---:|
| All audited players |5.12|5.49|5.38|
| Injury-affected teams,205 forecasts/14 games |4.74|5.69|5.43|
| Core diagnostic tier |4.32|4.77|4.95|
| Rotation diagnostic tier |4.94|5.26|5.27|
| Bench diagnostic tier |6.24|6.58|5.99|

Provider tiers above are evaluation strata only. Predictive tier assignment is independently derived and saved per row. Tier-specific recency helps the bench but still hurts core MAE, so the proposed clean removal of the trade-off is not supported. Overall >5-minute miss rate improves48.2%→44.7%, versus provider37.0%. Injury-slice miss rate51.7%→46.8%, versus provider31.7%.

The fresh boost fraction is0 in all five folds. Thus the combined candidate's change comes from tier-specific recency, not an empirically successful fresh replacement boost. An earlier-date family selector also keeps the original baseline in every fold; do not override that selection using verification outcomes. Fixed positive-boost proposal columns are retained for development audit without choosing a winning fraction post hoc.

On the broader37-game descriptive injury slice (244 forecasts), original5.55→tiered5.35 versus provider4.73. Do not mix these denominators with the29-game verification figures.

Conditional physical-game bootstrap, tiered minus original MAE: overall−0.113 minutes,95% interval−0.274 to+0.040; injury−0.177, interval−0.533 to+0.158. Neither establishes a credible gain. Injury tiered minus provider+0.780, interval+0.419 to+1.132 (game-weighted; differs from row-weighted table). These conditional intervals omit training uncertainty and multiple comparisons. The29 games have already informed development and are not a pristine external holdout.

## What remains unresolved
Consecutive missing-game inference cannot overcome absent participation records. No empirical ongoing-absence slice is available to verify the three-DNP heuristic. Recent participation also does not prove that all replacement minutes are still unabsorbed by teammate histories. The fresh-only mechanism should not be forced when earlier-date training rejects its boost. Roster completeness, new role transitions and return-from-injury handling remain unproven; no causal explanation of the full0.82-minute gap follows from this study.

58 targeted tests pass, including all previous49. New checks cover explicit three-DNP streaks, fresh cases, unknown gaps, two-missed transitions, future/same-day/completion cutoffs, duplicate calendar rejection, zero-minute ambiguity, history-based tiers and240-minute transfer conservation. All code remains on the offline research branch.
