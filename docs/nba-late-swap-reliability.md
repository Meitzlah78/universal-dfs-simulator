# NBA current-entry import and late-swap release

Release: `nba-entry-import-20261028-r2`.

## Behavior

DraftKings current downloads accept numeric IDs, Name (ID), and their `(LOCKED)`
annotations. Both `In Progress` and `Final` salary-table labels recover original
dated clocks using exact site player IDs, teams and salaries. No tipoff is guessed.
The salary clocks are retained as pool attributes through workspace snapshots and
remain authoritative when provider news has missing clock values.

The main importer tries the saved salary context, build pool and imported slate.
If all context is missing, it offers an original-pregame-entries upload in the
same screen. That upload supplies game metadata only; roster assignments and
entry IDs always come from the user's current entries file. Unknown or conflicting
metadata still blocks unsafe swaps. Ordinary exports also pass current pool
context to the parser rather than requiring a fresh pregame template.

The entrypoint activates this explicit release once in a long-lived Python
process, refreshing preloaded NBA dependencies and function aliases in dependency
order. It does not clear session data or outcomes. Bump the entrypoint release
identifier when deploying coordinated NBA module changes. The late-swap panel
shows import revision `2026-10-28 r2` to identify the new UI.

## Verification

`tests/test_nba_entry_workflow.py` covers status transitions, lost provider clocks,
snapshot restoration, same-screen context recovery, exact locked-slot preservation,
all-entry export, and replacement of stale reader/export function aliases.
`tests/test_nba_entry_workflow_ui.py` uses real Streamlit AppTest to restore the
context, import In Progress and Final downloads, run fast swaps, and expose an
enabled download. Related existing UI, auto-swap and simulated-swap tests passed.

Actual-file replay evidence is in
`docs/benchmarks/nba-late-swap-import-2026-10-27.json`: two DK downloads retain
20/20 entries; FD retains 48/48; 517 locked slots are checked unchanged. These
are local import/optimization/export checks at the recorded replay clocks.
They do not verify DK/FD platform submission, model quality, fresh projections,
or the deployed Streamlit Cloud process.

Live upload testing of the previous release reproduced the stale error. The
repaired metadata copy passed live main import. A later browser upload approval
was declined, so further file-upload testing in that browser must not be retried
without renewed authorization. Live read-only revision checks remain separate
from the local and AppTest results.

Started players may now have zero minutes, OUT status or an ineligible feed flag.
Late-swap validation preserves these immutable roster spots while continuing to
enforce current eligibility on all open selections. These overrides are made on
a validation copy only, never on the simulation or projection inputs.
