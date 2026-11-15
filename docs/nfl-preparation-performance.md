# NFL preparation performance and recovery

A market-enabled cold full-slate build now performs a three-pass preliminary
fit, market calibration and a full nine-pass final-context fit, followed by
separate evaluation and construction samples. Before the follow-up cold-fit
fix, both fits used nine passes. Without markets the only fit retains all nine
passes. See [the regression analysis](nfl-cold-fit-regression.md). A fitting
counter is not overall build progress. Reducing candidate count does not
shorten these fitting passes.

This change computes fixed player rates once per game, uses indexed stat
writes instead of repeated per-player masks, and skips empty draws. Draw order,
sample counts, fitting iterations, parameter bounds and scoring are unchanged.

Completed fitting passes and market calibration are atomically checkpointed
under the exact input/model key. After interruption, matching-input preparation
continues at the next unfinished pass. Completed evaluation and construction
samples are separately checkpointed, with hashes, names, dimensions and finite
values verified before reuse. A final bundle replaces those temporary sample
files. A corrupt checkpoint fails explicitly. Changed projections, roles,
weather, market targets, correlation, scoring platform or model cannot reuse a
different fit. Existing completed-fit and complete-bundle reuse stays intact.

The UI identifies pre-market fitting, market calibration, post-market fitting,
and final sampling separately. It reports elapsed fit time and an approximate
fit-only ETA after a complete measured pass. This is not a total build ETA.
When verified future kickoff clocks are within 20 minutes, it warns that a cold
build may miss lock. It does not block a user from continuing or promise a
completion time. Existing entry lineups should remain filled while building.

Checkpoints live on the same cache filesystem as prepared samples. They
survive a stopped/retried run while those files remain available; this does not
guarantee recovery after hosting replaces or deletes its filesystem. The current
unfinished pass/sample still needs to restart. The first run with changed code
has a new cache key and can still be slow.

## Validation

`tests/test_nfl_preparation_resume.py` checks interrupted fitting and construction,
skipping already finished work, exact resumed results, corrupted-checkpoint
rejection, monotonic progress, and preservation of the shipped scientific model.
Existing engine, scoring, preparation, projection, market, learning and injury
tests provide regression coverage.

`nfl-preparation-parity.json` records paired baseline/optimized timings and exact
seeded array comparisons on the two-team fixture and the supplied 240-player,
10-game November 15 input pool. Both sites are tested at 1,024 and 10,000 draws
with the existing learned rushing distribution, weather, market gains and player
input gains. Full nine-pass fit parameters and reports are also compared.
These are local measurements, not a Streamlit Cloud latency guarantee.

The immutable original learned version remains checked in. Its active index
points to an implementation-only revision bound to the changed code hash and
the parity evidence hash. Parameters, component validation, validation dates and
scientific acceptance remain unchanged. No holdout is reused for promotion and
no 2025 data is opened. This avoids silently falling back to the unlearned model
when the runtime checks engine compatibility.
