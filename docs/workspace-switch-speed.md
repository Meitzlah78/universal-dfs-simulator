# Shared NFL/NBA workspace switching

The shared DK/FD slate-tab handler copied the active workspace again immediately after autosave had already captured the same state. Autosave now returns its current-run detached capture to the tab handler. The handler reuses it only for the matching outgoing slate. Missing or mismatched captures retain the original fresh-copy path. Incoming restoration still deep-copies the saved checkpoint, preserving isolation from later edits and background backups.

Both NFL and NBA also loaded and verified calibration ZIP bytes while rendering their download buttons. An archived ZIP can require disk I/O or cloud retrieval. Diagnostic downloads now defer that work to the click when the installed Streamlit public API supports callable data. The deferred producer freezes the archive/owner and immutable content digest; it never reads mutable session state after switching sites. Pending in-memory bytes and older Streamlit versions keep their existing paths. Archive hash verification still runs on download. Entry CSV export, provider refreshes, simulations, ranking, exposure limits and model parameters are unchanged.

## Evidence and scope

The synthetic copy/restore benchmark uses 44 MB of outcome arrays. Seven paired runs reduced median copy/restore time from 0.0146 to 0.0110 seconds locally. This is a small isolated improvement, not evidence that copying dominates a long hosted switch. Raw measurements are in `benchmarks/workspace-switch-copy.json`; reproduce with `python scripts/benchmark_workspace_switch.py --output result.json`.

The larger structural improvement removes archived-package reads from initial rendering on supported Streamlit versions. Tests prove there is no archive `get` call before clicking and that the producer retains the original digest after switching slates. No fixed number of seconds is claimed for this change; it depends on package size, storage location and host performance. A real Streamlit AppTest verifies the download button renders without archive reads.

Validation: 56 Python tests pass across switching, session tabs, checkpoint/save behavior, cloud recovery, reboot restore, diagnostic packages and NBA export UI; one JavaScript tab-event test passes. NFL and NBA DK-to-FD-to-DK tests preserve portfolio rows, export bytes and simulation arrays. In-place edits remain isolated from frozen checkpoints, fallback captures preserve current changes, and tampered archived bytes are rejected. The cloud tests use mocked storage; no live cloud or hosted total-switch timing was measured.

This change is prepared for review without redeploying an active user session.
