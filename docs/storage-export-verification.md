# Workspace capacity and NFL export verification

## FanDuel payscale finding

The Monday DAL–PHI package selected the saved profile
`FanDuel:7000-thu-nfl-pooch-punt-20261022`. In `simmah_payscales.render_panel`,
the profile name is display metadata. The weekday is not parsed to choose a
date, determine ranks, select simulation arrays, or break ties. Selecting a
profile explicitly applies its numeric tiers, prize total and user-confirmable
field-size setting to the active contest.

Thus the label does not itself shift a payout timeline or corrupt ties. A wrong
selected ladder can still produce wrong monetary estimates, and its saved field
size may prefill a different contest's capacity. Structural consistency is not
proof the tiers belong to the Monday contest. Keep FD dollar results provisional
until independently confirmed against that contest's final payout schedule. The
saved schedule sums to $7,000; that check alone is insufficient. No historical
package, payscale name or payout tiers were changed by this verification.

The sample diagnostic referring to `metadata.json`, `standings.csv` and a
per-row `payout` column cannot run on these packages: they use `manifest.json`,
`inputs/contest.json`, separate standings uploads, and no actual paid-prize column.

## Isolated browser capacity probe

The app's explicit `?simmah_qa=storage` route renders an isolated diagnostic before
slate initialization. Open it in a separate tab. Normal app loads allocate nothing
for this diagnostic. Pressing **Run 512 MiB test**:

1. Creates a synthetic 536,870,912-byte ArrayBuffer and fills every byte with a
   known per-chunk pattern, yielding periodically to keep progress visible.
2. Commits it to IndexedDB database `simmah-storage-capacity-probe-v1` in one
   transaction, releases the original reference, closes and reopens the database.
3. Reads the stored buffer, verifies exact size/type and every byte, and records
   phase timings, event-loop delay, available browser long-task measurements,
   origin, user agent and quota estimates. It flags observed stalls over three
   seconds; timer/long-task measurements are diagnostic proxies, not a guarantee
   of smooth rendering.
4. Removes the synthetic database in success and failure paths. An explicit
   cleanup button handles interrupted probes. It never opens or deletes the real
   `simmah-workspace-backups-v1` database.

Quota failures retain their `QuotaExceededError` name. A pass applies only to the
tested browser/origin at that time; it is not a storage guarantee for Chrome,
Safari, private browsing, other profiles, or all future sessions. This isolated
buffer test does not validate ZIP serialization, static download, server RAM,
or full slate/widget restoration in Streamlit Cloud.

The component passes small 4 MiB unit fixtures for success, corruption and quota
failure, including cleanup and isolation from a real-backup sentinel. These are
unit fixtures, not evidence of a live 512 MiB browser pass. The route also passes
Streamlit AppTest without initializing active-slate state.

After the owner's reboot, probe version `storage-probe-v2-latency` was visibly
available on the deployed app and the real cloud Chrome browser run completed:

| Metric | Measured result |
|---|---:|
| Logical buffer verified after database close/reopen | 536,870,912 bytes |
| Write | 0.5872 seconds |
| Read | 0.7606 seconds |
| Verification | 0.2504 seconds |
| Total | 1.9343 seconds |
| Maximum timer-based event-loop delay | 712.6 ms |
| Maximum observed long task | 753 ms |
| Observed stall over three seconds | No |
| Synthetic test data removed | Yes |

No quota exception occurred. The result applies to the dedicated cloud Chrome
browser, not the user's Windows browser or Safari. A sub-second pause was measured;
this is not zero-lag operation. See `benchmarks/workspace-browser-capacity.json`.

The synthetic per-chunk constant pattern is highly compressible. IndexedDB's
reported usage rose only to approximately 24 MiB, so this verifies a 512 MiB
logical ArrayBuffer round trip but does not prove sufficient physical quota for
an incompressible 512 MiB ZIP. An incompressible payload is needed for that claim.
The timing/usage estimates also do not prove durable storage across a browser
process crash or storage eviction.

This browser run sends only its small telemetry report to Streamlit; it does not
perform the heavy ZIP restore in the Cloud container. That host-memory test
remains unverified. Do not reboot an active workspace merely to rerun a diagnostic.

## Near-limit ZIP/server recovery

An isolated local run used a 511 MiB incompressible random byte array. Its typed
ZIP was **511.15598 MiB**, below the 512 MiB archive-byte limit. Recovery used
**715** bounded frames, verified the archive hash, restored the full array, and
confirmed exact array equality. The run took approximately **31.4 seconds** in
the local executor. See `benchmarks/workspace-capacity-local.json`.

The cap applies to the entire compressed ZIP, including headers and manifest;
a 512 MiB source array does not necessarily fit a 512 MiB archive cap. This test
is local evidence, not a Streamlit Cloud server-memory benchmark.

## Native CSV acceptance audit

`simmah_export_audit.verify_entry_export` accepts the original native CSV, an
exported CSV, original salary metadata keyed by exact site ID, site/mode,
explicit contest scope and optional expected Entry-ID-to-roster assignments.
It checks:

- Original/exported IDs are exact positive integer strings, unique and equal
  within the explicitly selected contest scope. Unselected entries are counted
  as excluded rather than incorrectly reported as missing replacements.
- Contest ID, contest name, fee and other included entry metadata remain
  unchanged. Optional assignment parity compares each entry's ordered roster.
- All player IDs exist in original salary metadata; no athlete appears twice,
  including through different DK CPT/FLEX IDs. FD IDs match the slate prefix.
- DK Classic has nine slots and a $50,000 cap; FD Full Roster has nine slots and
  a $60,000 cap. QB/RB/WR/TE/FLEX/defense eligibility is checked. DK Classic
  requires two games, and FD Full Roster enforces its four-player team maximum.
- Six-player single-game rosters use both teams. DK's role-specific IDs must
  match CPT/FLEX and carry original role-priced salaries. FD's MVP uses 1.5x
  its base salary, with a $60,000 total cap.

FD's original embedded reference/instruction rows are preserved. DK's valid
roster-only replacement format may omit instruction/reference columns and rows;
its pandas duplicate-header suffixes are normalized for semantic comparison.
This is explicitly reported rather than falsely requiring byte-identical native
CSV headers or instructional footers across both sites.

Using the two saved DAL–PHI packages, the audit regenerated files through the
current production export functions, with the unchanged captured selector and
original embedded salary tables. Both passed:

| Check | DK Showdown | FD Single Game |
|---|---:|---:|
| Original entries checked | 20 | 60 |
| Missing/extra/repeated entry IDs | 0 | 0 |
| Contest or assignment changes | 0 | 0 |
| Salary/role violations | 0 | 0 |
| Repeat replacement bytes identical | Yes | Yes |

The generated exports were not uploaded. There is no exact captured final
submitted-export artifact in these packages, so this does not prove what bytes
were previously submitted or how a future site upload will respond. The earlier
standings match independently establishes which rosters were actually entered.
See `benchmarks/export-acceptance-2026-10-26.json` for hashes and aggregate results.

## Reproduce the checks

```bash
python -m unittest discover -s tests -p test_export_audit.py
python -m unittest discover -s tests -p test_exports.py
python -m unittest discover -s tests -p test_dk_contest_export_scope.py
python -m unittest discover -s tests -p test_fd_entry_column_isolation.py
node tests/test_storage_probe.cjs

# Local heavy benchmark; do not launch it inside the production app:
python scripts/benchmark_workspace_restore.py --mib 511 \
  --output docs/benchmarks/workspace-capacity-local.json

python scripts/audit_saved_entry_exports.py \
  "$INPUT_DIR/Simmah_NFL_DraftKings_Showdown_197055079_20261027T000509Z_15fa387795_Calibration_Solver.zip" \
  "$INPUT_DIR/Simmah_NFL_FanDuel_Single_Game_135830-281254012_20261027T000748Z_a52181a768_Calibration_Solver.zip" \
  --output docs/benchmarks/export-acceptance-2026-10-26.json
```

Remaining gates are incompressible browser quota testing, a complete ZIP/slate
reboot recovery in Streamlit Cloud under actual resource limits, final site
upload acceptance, and independent confirmation of the FD payout ladder.
