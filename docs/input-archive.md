# Original inputs and automatic historical calibration

Every upload through the shared salary/entries uploader and the format-specific
uploaders is captured before parsing, including multi-file contest imports.
Original bytes, filename, capture time, SHA-256 and classified slate metadata are
retained. Same-byte uploads deduplicate; different salary revisions are distinct.
No raw originals are committed to the public source repository.

## Storage and recovery

The browser keeps originals in a separate IndexedDB database named
`simmah-original-inputs-v1`. Closing a Loaded Slate does not delete this database.
On reconnect, missing server files are recovered from that browser and checked
against their hashes. Browser storage can still be cleared or evicted. A browser
identity is not a cross-device account or an off-device backup.

The server stores inputs and job results under `SIMMAH_ARCHIVE_DIR` (default
`data/input_archive`). Its per-browser subdirectories and SQLite indexes are
excluded from Git. On Streamlit Community Cloud the default host filesystem can
be replaced on restart/redeploy, so this copy is explicitly labelled local.

For a durable off-host copy configure a private S3/S3-compatible bucket in
Streamlit secrets:

```toml
[input_archive]
bucket = "YOUR-PRIVATE-BUCKET"
region_name = "us-east-1"
prefix = "simmah-inputs"
aws_access_key_id = "CONFIGURE-IN-SECRETS-ONLY"
aws_secret_access_key = "CONFIGURE-IN-SECRETS-ONLY"
# endpoint_url = "https://your-s3-compatible-service"
```

Use a private bucket with public access blocked and credentials limited to the
chosen prefix. No credentials enter reports, browser records or logs. No bucket
or paid account is created by this change. Boto3 may also use the host's normal
credential chain. S3-compatible services must support AES256 server-side
encryption and object metadata. A file is counted as durably backed up only
after both original and metadata writes succeed; errors stay visible.
The durable metadata index is recovered automatically for the same browser
identity after host replacement; original object hashes are verified on fetch.

The archive panel downloads each original or a combined backup ZIP, and restores
backup ZIPs into the current browser namespace after verifying every original.
Keep a downloaded backup to recover across browsers or devices. The browser
identity is required to locate its cloud namespace; a new browser does not
silently list another browser's files.

## Automatic matching and fitting

Completed standings are audited for complete/missing entries, unique canonical
rosters, exact multiplicity spectrum, and identical-entry pairs. CPT/MVP identity
is preserved and FLEX order is ignored. Empty rosters never enter denominators.
DK `TimeRemaining` values must all be zero. FD sources lacking that field are
treated as completed standings as declared by their upload context; finality is
not independently confirmed through a platform API.

An expensive fit is scheduled only for a salary/entries table and contest file
sharing platform, roster mode and an exact embedded contest ID. The full parser
then rechecks player mappings, salary legality, teams and score consistency.
Ambiguous salary revisions are not silently selected. A standalone salary table
without a contest ID is retained but does not automatically trigger a name-only
match. No current player pool or FanDuel/DraftKings substitute is used.
For salary-only files without a contest ID, the panel allows an explicit
same-slate confirmation and binding. Conflicting embedded contest IDs cannot be
overridden. All salary/score/identity checks still run after that confirmation.

Current exact fitter coverage is NFL DK Showdown, six-player FD Single Game,
and NBA Classic on both sites. NFL Classic/full-roster and unidentified files
are retained and audited but never labelled as exact-KL calibrated by this
implementation. The panel exposes `unsupported_format` or a waiting message.

The NBA fitter uses canonical physical-player sets. A deterministic family of
reachable slot assignments prevents multiple eligible slot arrangements from
overcounting the same roster. Source-assignment eligibility, unique players,
salary, team/game limits and scores are checked before optimization. NBA targets
are normalization and all player inclusion marginals; NFL stack features are not
reused. Zero-ownership players are excluded only on this historical active face,
and ownership-one players are forced. Exact modular witnesses are supplemented
with rational reconstruction and global integer-DP extrema before any feature
dependency is removed. No sampled-support substitute or ridge is introduced.

The default NBA construction budget is 4,000,000 stored states and 90 seconds.
`SIMMAH_NBA_MAX_STATES` can be set between 1,000 and 20,000,000 for appropriately
sized hosts. Exceeding a budget retains inputs and a downloadable stopped-run
diagnostic; it is not reported as infeasibility or verified convergence. The
saved DK night-slate test (contest 196711762) validated 7,037 complete entries,
2,553,158,784 canonical active rosters, and a 4.60e-10 ownership residual. This
does not establish capacity for every larger NBA slate or predictive accuracy.

Matching single-game inputs invoke the previously validated integer/log-DP,
float64 warm fit and GCC binary128 refinement in a separate subprocess. Original
probability-unit gates remain unchanged: raw gradient <= 1e-9, reconstructed
constraints <= 1e-8, normalization <= 1e-12, finite values, and independent rounded
float64 verification. An optimizer exit flag alone never certifies convergence.

One background fit runs per app process, numerical libraries use one thread,
and a subprocess has a 30-minute budget. Accepted-step/evaluation logs, original
hashes, exact results and a downloadable result ZIP are retained per attempt.
Interrupted attempts are preserved and restarted into a new directory after a
process restart when their files are recovered. Failed fits remain failed; they
are not silently promoted or retried on every UI rerun.
Each job snapshots and hashes its engine source files before launch, so a code
update cannot change the C kernel halfway through a running calibration.

Live Run Build/BUILD NBA actions take priority: no new calibration launches
while a build is active, and an already-running Linux calibration process group
(including its GCC/native child) is paused until the build finishes. Paused time
does not consume the calibration worker timeout. Allocated solver memory remains
resident, so no zero-overhead performance claim is made. A stale build lease is
released on the next full rerun or after 30 minutes. Other operating systems
defer new jobs but do not have this Linux process-group suspension behavior.

These fits are retrospective diagnostics, not estimated pre-lock ownership or
out-of-sample validation. They do not automatically change live projections,
opponent construction parameters, payouts or ROI estimates.
