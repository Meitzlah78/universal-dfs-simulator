# Simmah workflow target

Mark's target is a workflow close to SaberSim's publicly documented process.
This is a functional target, not a claim of equivalent private algorithms,
projections, forecasts, win rates or profitability.

## Current implementation

All four NFL formats use shared game outcomes and the joint-outcome candidate
search. One SIM action produces 10,000 evaluation outcomes and a separate set of
10,000 construction outcomes. Candidate proposals optimize individual complete
slate scripts using batched greedy seeds and coordinate ascent. This is bounded
heuristic search, not a globally optimal solver. The target is 5,000 unique legal
candidates; infeasible/tight pools return a visible shortfall rather than padding
with duplicates. Salary, role multipliers, locks, stack choices, team limits and
Captain exclusions are enforced. Lineup percentiles use actual joint score sums,
not sums of marginal player percentiles.

Completed-contest uploads now create anonymous feature profiles that are consumed
by all opponent-field paths. Matching uses exact sport/site/format/roster size;
known stakes/entry limits do not silently back off to conflicting known contexts.
Unknown metadata is labeled as such. An oversized legal proposal field is sampled
without replacement using bounded historical/source density ratios. This does not
add artificial duplicate rows or transfer old player names to the current slate.

The checked-in seed contains 85,752 valid DK Classic entries. It learns ownership
concentration only: historical salary/team metadata was not available in that
standings file. New imports can add salary and QB-stack/bring-back/RB-defense
features when a matching historical player metadata file is supplied. Profiles
for other formats require matching imports; otherwise the baseline is disclosed.

Profile files contain aggregate histograms, context and hashed identities, not
player/user names, entry IDs or actual fantasy scores. Same-contest ZIP/CSV and
row-order variants deduplicate by hashed entry identities. Imports are atomically
merged under a lock. Host-local storage survives reruns/sessions, but hosting
redeploys can erase it; backup/restore controls provide portability. The checked-in
seed survives redeploys. This is not an external durable database service.

DK Classic now evaluates all 10,000 outcomes in streaming batches, splits prizes
across occupied tie positions, and evaluates selected portfolios jointly. Changing
the displayed Classic portfolio uses cached joint scoring and exports those
reviewed lineups. The representative opponent field is still estimated.

## Remaining acceptance work

| Area | Remaining work |
| --- | --- |
| Football model | Held-out calibration of player distributions, tails, game totals and correlations; regulation-only assumptions still omit football events |
| Candidate search | Compare heuristic solutions against exact small-slate solutions and held-out real contests; validate portfolio performance, not just legal rosters |
| Opponent fields | More source contests with historical metadata, separate stakes/entry-limit coverage, duplicate-frequency and ownership validation on unseen slates |
| Contest definitions | Verify real size, fees, entry limits and payout provenance for every contest; preset/fallback structures must not be mistaken for live confirmation |
| Portfolio | Unify joint-return diversification and per-contest groups across the site-specific interfaces |
| Exports | Expand official-template fixtures across all formats and multi-contest uploads |
| Deployment | Verify the complete Streamlit workflow and resource use on the actual host; provide an external durable profile store if needed |
| Late swap | Separate implementation for kickoff locks, available players, updated outcomes and portfolios |

Passing syntax/unit tests verifies mechanics, not forecast calibration or SaberSim
parity. Keep these remaining gaps explicit until measured against unseen contests.

## Public references reviewed 2026-10-17

- Workflow: https://support.sabersim.com/en/articles/17506516-how-do-i-build-lineups-on-sabersim
- Per-outcome construction: https://support.sabersim.com/en/articles/17506514-why-do-i-get-different-lineups-when-i-build-again
- Contest simulations: https://support.sabersim.com/en/articles/17506264-how-do-contest-sims-work
- Field/contest definitions: https://support.sabersim.com/en/articles/12079199-how-contest-sims-work
- Custom ownership/fields: https://support.sabersim.com/en/articles/17506876-how-do-i-use-my-own-ownership
- Contest groups: https://support.sabersim.com/en/articles/17506489-how-do-i-build-lineups-for-a-specific-contest

### Classic field audit (October 17, 2026)

The uploaded 10,000-opponent field had 58% unstacked quarterbacks, while the
candidate pool required a QB/pass-catcher stack. The old stack preference also
counted RBs. Classic opponents now require at least one same-team WR/TE with the
QB, independently of user-selected stack rules. This is an explicit tournament
baseline, not a learned population frequency. Nine-player teams and repeated
players are rejected; salary limits and duplicate opponent lineups are preserved.

A construction replay using marginal means recovered from the uploaded rounded
lineup totals produced 10,000 valid opponents, with mean points 101.55 versus
101.47 previously. This verifies roster mechanics, not ROI calibration. Exact
outcome-based finish rates cannot be reproduced from marginal means alone.
