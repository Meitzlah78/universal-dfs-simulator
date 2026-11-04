# Recovering exposure-limited NBA portfolios

Increasing integer-solver effort alone did not resolve the reported failure. A reconstruction from the November 4 uploaded DraftKings pool reproduced the repair timeout for a 20-entry portfolio. The continuous relaxation was feasible; that does not establish integer feasibility within the original 5,000-candidate pool.

The pipeline now makes one bounded attempt to broaden candidate coverage after the specific repair-limit/no-full-portfolio errors. It searches up to 1,500 additional candidates from the SAME construction outcomes with search-noise preference 0.6 (normal search remains 0.15), seed construction seed + 3001, and the same salary, eligibility, team, correlation and exclusion rules. All original candidates are retained. Cross-pool roster duplicates are removed before scoring. Added candidates are evaluated on the SAME independent evaluation outcomes against the SAME opponent field and payout schedule; no new game-simulation sets or future results enter recovery.

Selection then retries with all original hard limits. A successful recovery reports the additional candidate count and stores its search settings in the diagnostic bundle. The actual candidate pool can therefore exceed the requested 5,000 during recovery. These are additional alternatives, not additional submitted entries or forced exposure targets.

The shared repair helper also expands a fractional relaxation's support with low reduced-cost alternatives. A fractional optimum's positive support may contain no integer solution even when the full candidate pool does. The two supported integer attempts share the prior two-second budget (one second each), followed by the existing full-pool fallback. Every returned portfolio still passes the original count and bound checks.

## Current-pool verification

The supplied DK CSV has 382 rows, 232 eligible players and RotoWire ownership totaling 799.5%, accepted by the existing 800% normalization rule. Reconstructed construction settings: 10,000 scenarios, seed 83, search seed 84, $48,000 salary floor, correlation 0 and team implied totals from the CSV. The normal search generated 5,000 candidates. A repair-only comparison using construction mean points as a quality proxy timed out for 20 entries in both the previous and expanded-support solver, while both selected 101 entries. Broader candidate support then allowed 20 valid entries. This comparison is not an exact replay of the missing live scored pool.

A complete controlled pregame replay used 20 entries, diversity 50, the archived DK $250 Dime Time ladder (2,972 capacity, $0.10), the uploaded pool's ownership, and three independent sets of 10,000 scenarios. It reproduced the initial repair error, added 1,495 unique candidates and returned 20 unique entries satisfying the hard limits in 53.56 seconds on the test machine. The live contest/payouts and other hidden settings were not supplied, so the test does not claim exact live parity. Browser rendering, export and diagnostic ZIP capture are outside that timing.

## Failure evidence

If selection still fails, the exception preserves aligned candidate indices, scores and settings. The Build tab offers **Download failed portfolio diagnostics** and queues that ZIP through the existing private archive. The bundle includes the frozen player pool, candidate rosters and scores, derived hard limits, selection version, contest/settings, implementation files and hashes. It is labelled a selection failure, not a successful build or model-training outcome. It does not bypass export checks or silently use a smaller portfolio.

The benchmark summary is `data/nba_speed_trials/2026-11-04-current-dk-candidate-recovery.json`. New regression tests verify preservation of original candidates, exclusions, construction/evaluation seeds, field and report alignment, plus recovery-failure capture and archive integrity. Selection version is `quality-role-exposure-v5-expanded-repair`.
