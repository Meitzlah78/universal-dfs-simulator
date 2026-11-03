# Multi-format portfolio replay

`python scripts/replay_portfolio_methods.py --build frozen.zip --standings results.zip --slate-group NBA-2026-11-03-main --output replay.json --ledger ledger.json`

Supports NFL DK Classic/Showdown, FD Full Roster/Single Game, and NBA DK/FD through the same frozen-build loader as the ranking comparison. `--trials` defaults to 1,000, `--seed` to 20261103. This is an offline audit, not automatic monitoring or a change to live selection.

## Fixed selection protocol

Use the entire frozen candidate pool. Deduplicate interchangeable slots while retaining Captain/MVP identity. Never filter using published actual-score coverage or a hindsight-derived top-250 cutoff. All method selections finish before standings are opened.

- Deterministic: saved Top 1% metric and saved diversity setting, current shared selector.
- Diversity sweep: settings 0, 25, 50, 75, 100 using the same Top 1% metric.
- Distance: seed the highest pregame Top 1% candidate, then minimize maximum normalized player overlap, with pregame order breaking ties.
- Constrained random rejection: uniform fixed-size samples without replacement, accepted only if all hard limits pass. Stop after 100 times the requested trial count. If the requested count is not reached, report the benchmark unavailable rather than silently relax limits or summarize a smaller sample.
- Separate random-swap benchmark: start at the valid deterministic portfolio, propose uniform outgoing positions/incoming candidates, and accept only distinct candidates preserving all hard limits. Burn in for 100 times portfolio size proposals and retain a sample every portfolio-size proposals. This dependent chain has no established mixing/convergence guarantee and is not described as a uniform sample. Seed is base seed plus one.

The random methods are distinct benchmarks. Preserve their identities in later comparisons; do not choose whichever did better after results.

## Identical hard constraints

Overall ceilings and minima, locks/fades, Captain/MVP minima and maxima, and FLEX maxima use the shared selector's floor/ceiling rounding. No manual hard constraint relaxes. Automatic diversity caps are soft selector preferences, not newly imposed hard limits for random/distance methods. Report the effective automatic cap for each selector run.

Every method samples whole saved candidate rosters without changing positions or combining players. Salary, positional eligibility, team limits and stack rules are inherited from the frozen builder's candidate pool. This does not independently certify the builder's legality or reconstruct unavailable historical generation settings. A QB stack is not universally mandatory. If builder legality itself is suspect, validate that pool separately before treating its replay as a clean experiment.

Distance is intersection size divided by roster size, so eight- and nine-player rosters share a 0–1 scale. For fixed roster size, Jaccard is a monotonic transformation and gives the same farthest-first ordering. Special roles affect candidate identity, while this distance measures overall player overlap, not role-weighted overlap or outcome covariance.

A greedy distance dead end is reported as a search failure, never as proof of infeasibility. Random swap benchmarking is unavailable if no valid deterministic seed exists.

## Evaluation and dependent groups

Remove all identified original entries and insert the whole counterfactual portfolio together, splitting ties including own entries. Preserve unknown portfolio returns when player actuals are unpublished; never drop or zero-fill a lineup. Do not summarize random net returns conditionally on which draws happen to have published scores.

Record net return, paired dollar delta versus deterministic selection within that contest, best rank, cashing entries, maximum player exposure, squared exposure sum and selected-roster hash. Random trial records retain those values individually; summaries give mean, median and losing frequency only with complete actual coverage. Monte Carlo trials are not independent slates.

The ledger nests contests under an explicit shared slate-group label. DK and FD portfolios sharing player outcomes belong together. Reruns replace the same contest record rather than add observations; assigning the same contest to a second group is rejected. The ledger does not infer independence from different contest IDs or aggregate an inferential win rate.

Existing NBA archives lack hidden historical manual overrides. Their replay uses current hard limits derived from the frozen player pool, with that limitation retained in reports. Existing October/November cases are retrospective integration checks, not forward validation. New protocol versions/settings must be fixed before inspecting later outcomes. No live method is promoted by this code.

## Retrospective integration run (November 3)

Six saved formats were exercised with 1,000 requested rejection draws and 1,000 swap-chain samples per case. Four sizes were present: 11, 17, 20 and 111 entries. NFL DK/FD main slates share one group; NBA DK/FD share another; Monday CHI–SEA DK/FD share a third.

| Format | Rejection benchmark | Swap benchmark |
| --- | --- | --- |
| NFL DK Classic | 1,000 valid; 771 fully scored, aggregate return unknown | 1,000 valid; 768 fully scored, aggregate return unknown |
| NFL FD Full | 1,000 valid; 480 fully scored, aggregate return unknown | 1,000 valid; 461 fully scored, aggregate return unknown |
| NBA DK | 0 accepted within 100,000 draws; unavailable | 1,000 valid; missing actuals, return unknown |
| NBA FD | 943 accepted within 100,000 draws; incomplete benchmark | 1,000 valid and fully scored |
| NFL DK Showdown | 1,000 valid and fully scored | 1,000 valid and fully scored |
| NFL FD Single | 1,000 valid and fully scored | 1,000 valid and fully scored |

Partial score coverage is not used to discard random trials and report an optimistic conditional result. These inspected slates do not authorize changing live settings. Summary reports and the grouped ledger are retained under `data/engine_validation/`; full trial records are emitted by the CLI for new runs.
