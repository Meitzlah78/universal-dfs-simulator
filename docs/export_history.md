# Saved export history

Every NFL entry-export click creates a new version, including identical downloads.
The shared download wrapper also captures NBA entry exports and late-swap exports
AFTER lock reconciliation. Review-report downloads do not replace the latest
entries export. Generation, projections, ranking and site upload bytes are not
changed by archiving.

Each ZIP contains the exact downloaded CSV, export ID/time, format/contest
identity, parent export reference, SHA-256 manifest, the export-time player table
and its attrs, and a serialized workspace containing available candidates,
scenarios, fields and controls. NBA captures explicit build/portfolio objects;
late swap includes the original uploaded CSV, reconciled result and portfolio.
Unsupported/oversized workspace values appear in its omitted list. This is not
a guarantee of full original-build provenance, provider retrieval timestamps,
or successful submission to the site.

Saved exports appear below the export control in "Saved exports — latest first".
Users can download an older exact CSV or its audit ZIP. History is stored in the
browser-owned slate workspace and a separate exclusive server ZIP copy. The
completed-contest review prefers the last entries/late-swap export with matching
format and contest ID. If none is available it labels the legacy snapshot fallback.
Archive errors are surfaced; they do not silently report a successful save.

Browser storage can be cleared and hosted server disks may be replaced. Download
an archive or workspace backup for independent retention. Server copies are not
cross-user lookup sources. No automatic upload to GitHub or third-party database
is performed, and no checkpoint proves DraftKings/FanDuel accepted an upload.

Seven unit checks cover repeat versions, latest-contest selection, late-swap
lineage, exact CSV/hash preservation, browser state roundtrip, no-overwrite server
storage, and callback binding. Existing snapshot regression checks also pass.
