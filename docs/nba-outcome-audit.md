# Automatic NBA outcome check

Saved NBA builds now evaluate their frozen player outcomes when the Build or
Lineups export section renders and matching completed box scores are present
in the nightly archive. Open **Automatic NBA outcome check** to see each seed's
projection error, simulated-mean error, minutes error, and P10/P90/P99 coverage.
The JSON download includes player rows and every omission.

This runs without an extra upload or button for a saved build whose diagnostic
package is available. Results are cached by package digest and the relevant
archive files; new/replaced box scores invalidate the cache. Only the slate's
dates are loaded. It does not run while the app is asleep: GitHub's nightly job
has box scores but does not have the private saved forecast packages. Opening
the saved slate completes this comparison automatically. Missing archive data
shows pending rather than a passing grade.

The audit verifies frozen CSV/array checksums, aligns outcome columns with the
frozen pool, and matches date, normalized name, team and opponent. Explicit DNPs
score zero; unknown/missing rows remain omitted. Captures at or after a player's
scheduled start are excluded. Existing timezone-less provider clocks use the
Eastern wall-time convention already used by the NBA importer. Platform scoring
includes DraftKings bonuses and FanDuel defensive scoring.

Each seed evaluates the same players: counts must not be summed across seeds.
Repeated builds should be reduced to the last pretip capture per player/game/site
for pooled analysis. DK and FD outcomes also overlap. Player observations share
games and dates; coverage on one slate is not a confidence guarantee. The 70%
coverage warning is an operational diagnostic flag, not a promotion gate.

CLI: `python scripts/audit_nba_outcomes.py ORIGINAL_BUILD.zip --output audit.json`.
For a latest-export wrapper, use its contained `original_build.zip`. Raw packages
and audit reports contain private inputs and should not be committed publicly.

The live pregame engine repeats projected regulation minutes across scenarios;
random rotation ordering does not model uncertainty in total regulation minutes.
The existing empirical minutes challenger remains offline. Historical-role
learning evaluates stat counts conditional on actual minutes, so passing that
gate cannot establish pregame minutes or fantasy-score tail calibration. This
change measures that gap; it does not modify simulations, projections, exposures,
selection or learned model versions.
