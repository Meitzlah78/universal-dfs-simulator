# Simmah workflow target

Requested by Mark: make Simmah operate as closely as practical to SaberSim's
publicly documented workflow. This is a functional target, not a claim of model,
forecast, return, data-provider or proprietary algorithm equivalence.

## Target experience

Upload the entries/slate file, verify projections and injuries, run shared game
simulations, build the candidate pool from those outcomes, simulate each entered
contest, diversify its portfolio, review exposures, then replace existing entries.
Keep uploaded projection priority, DFF/DraftEdge availability, injury filtering,
10,000 independent outcomes, 5,000 candidates and format-specific roster rules.

## Current gaps and acceptance criteria

| Area | Current state | Required next behavior |
| --- | --- | --- |
| Football outcomes | Shared independent regulation simulation, tested event/scoring accounting | Validate out of sample against actual player/game distributions, tails and pair correlations; expand omitted football events |
| Weather | Shared venue/kickoff forecast affects game events | Validate coefficients; improve roof metadata and unmapped venue coverage |
| Candidate construction | Weighted random generation still relies mainly on marginal summaries | Optimize rosters against sampled joint outcomes, preserving salary, stacks, exposures and pool size; compare against current generator on held-out simulations |
| Opponent fields | Ownership signals and construction heuristics | Persist parsed completed-contest features; actually fit and consume field profiles separated by site, roster format, entry fee and entry limit |
| Contest definitions | Entry import, contest selection, payout libraries/fallbacks | Validate exact size, fee, entry limit and payout provenance for every selected contest; identify estimates explicitly |
| Contest scoring | Shared-outcome ranks, payouts and tie logic exist | Fixtures against known complete fields, duplicates and payout ladders; holdout checks for selection bias and implausible returns |
| Portfolio | Ranking/exposure/diversification features exist, differ by format | Select contest-specific portfolios using joint returns, overlap and exposure feasibility; reuse candidate pools when sorting changes |
| Historical feedback | Reports plus session registry; generic learning functions not wired to builders | Durable, deduplicated contest-feature storage and visible evidence that an applicable profile was used |
| Entry replacement | DK/FD replacement exports exist | Regression fixtures for IDs, contests, slot order and all owned entries across the four formats |
| Late swap | Not established in this audit | Separate project: kickoff locks, eligible replacements, updated games/fields and portfolio re-evaluation |

## Implementation order

1. Finish the current shared weather integration and regression checks.
2. Wire real completed-contest ingestion to persistent field features and profile
   selection. Add explicit counts, profile provenance and fallback status.
3. Replace summary-driven candidate generation with simulation-driven roster
   optimization; assess it on independent evaluation outcomes.
4. Validate contest metadata, tie splitting, duplicates and field realism before
   describing estimated ROI as calibrated. Group portfolio/export by contest.
5. Unify the review/rebuild/export experience, then implement late swap separately.

A passing syntax check or a large projected ROI is not evidence of parity.
Completion requires behavior fixtures and held-out completed-contest evaluation.

## Public references reviewed 2026-10-17

- Build/review/diversify/export workflow:
  https://support.sabersim.com/en/articles/17506516-how-do-i-build-lineups-on-sabersim
- Per-outcome candidate building:
  https://support.sabersim.com/en/articles/17506514-why-do-i-get-different-lineups-when-i-build-again
- Contest reconstruction and game-outcome scoring:
  https://support.sabersim.com/en/articles/17506264-how-do-contest-sims-work
- Field behavior and contest definitions:
  https://support.sabersim.com/en/articles/12079199-how-contest-sims-work
- Custom ownership must be used to construct a field:
  https://support.sabersim.com/en/articles/17506876-how-do-i-use-my-own-ownership
- Contest-specific lineup groups:
  https://support.sabersim.com/en/articles/17506489-how-do-i-build-lineups-for-a-specific-contest

These pages describe public behavior; they do not reveal SaberSim's private
football model, optimizer implementation or learned field parameters.
