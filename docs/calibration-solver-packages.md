# Calibration and solver packages

After a successful scored NBA or NFL build, use **DOWNLOAD CALIBRATION & SOLVER
PACKAGE**. NBA exposes it with lineup exports; NFL exposes it above Saved files
at the bottom of the workspace. The same package is queued automatically in the
existing private archive. Filenames identify sport, platform/format, contest,
capture time and immutable identity. Original uploads remain private; no input
or generated diagnostic files are committed to Git.

NBA packages preserve the full build pool, original entries/salary bytes,
contest/payout settings, rules, markets, three exact shared outcome matrices,
unsampled opponent support, fitted probabilities/parameters, sampled field and
copy counts, scored candidates, initial portfolio, seeds, engine reports and
installed model/solver source snapshots. Ownership fallback is retained with its
warning and residuals. Requested build sizes are unchanged.

NFL packages cover DK Classic/Showdown and FD Full Roster/Single Game. They
preserve the exact scored field, player pool, candidate/results tables, active
slate upload, relevant controls/ownership/market/weather state and matching
prepared outcome/fit cache artifacts. The active evaluation matrix is stored
independently in NPZ so workspace serialization limits cannot omit it. Missing
cache artifacts or other evidence are listed in the manifest. No cache is
refitted or guessed from modification times.

Every member listed in the manifest has a SHA-256 checksum. Exact capture times
are recorded in UTC and Eastern. Capture alone is not proof of a pre-tip forecast,
site submission or out-of-sample performance. Completed standings are a separate
postgame input. Representative fields remain representative: the package records
the actual scored field without silently padding or resampling.

Downloading an entries or late-swap export automatically attaches its audit
checkpoint to the matching original build. The updated package contains
`original_build.zip` and `latest_export_checkpoint.zip`, preserving the original
forecast and latest exact exported CSV with available lock/swap details. Reports
and other contests/formats cannot replace the latest entries checkpoint. Later
updates reuse the untouched original build, without recursively nesting previous
combined packages. The original and earlier checkpoints remain archived.

Historical solver reports now retain source inputs, engine source, provenance,
stdout/stderr and fit outputs for successful, budget-stopped and failed attempts.
Rebuildable binary frontiers, compiled executables and nested archives are omitted
explicitly in `package_manifest.json`. Those reports remain available under
Saved files & automatic calibration, including the existing job report download.

Storage follows the existing archive: server/browser retention and optional
private durable backup. Save failures remain visible and do not erase lineups.
A downloaded ZIP is an independent backup. Large package bytes are kept out of
slate snapshots; workspaces retain immutable references and recover package bytes
through the private archive. Legacy builds must be rebuilt once to capture
evidence that was never retained.

Validation:

```sh
PYTHONPATH=tests:. python -m unittest test_diagnostic_packages test_nba_pipeline \
  test_nba_field test_nba_popularity_fallback test_nba_ownership_fallback \
  test_export_history test_slate_workspaces test_input_archive test_nba_ui -q
```
