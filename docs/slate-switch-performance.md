# Prioritize slate switching and avoid provider-metadata copy fanout

The saved DK diagnostic build used for this audit contains 5,000 candidates and a 20-entry portfolio. Its retained workspace-routing, roster-validation, player-label and DK-import source files match the original main implementation used as this fix’s base. No game outcomes, final box scores, or confirmation grading were opened; no basketball simulation was run during navigation profiling.

## Findings and fixes

1. Session-tab events were consumed in `finish_workspaces`, after the old slate had already passed through its preparation, display and export path. Events already present in Streamlit session state are now consumed at the beginning of `begin_workspaces`, before persistence recovery and old-page preparation. The latest current state is detached once, the destination restores in the same run, and completed events cannot replay. Inactive checkpoints remain queued for durable backup after the switch; the navigation action does not wait for cloud uploads.
2. NBA roster validation built a full indexed DataFrame/dictionary for each lineup. Pandas copied the raw provider evidence in DataFrame attrs during column boxing. One profiled 20-lineup export made 30.7 million recursive deepcopy calls; practically all its cost was metadata copying. Validation now reads the same row values from a NumPy-backed view. Distinct players, positions, injuries, projections, minutes, salary, teams, games, exposure and reserved-entry checks remain enforced. Duplicate pool IDs are explicitly rejected.
3. Player-label rendering repeatedly filtered and boxed full player rows carrying the same evidence. It now works on a small display-only frame with only the lineup-pending attribute needed for label semantics. Original provider metadata, raw player names, and model inputs remain intact. Label output was identical on the saved DK pool.
4. Started-game DK clock recovery repeatedly filtered the entire provider-backed context frame for each player. It now builds one metadata-free lookup while retaining duplicate-ID, team, salary, opponent and start-clock validation.

## Local replay evidence

| Operation | Before | After | Verification |
|---|---:|---:|---|
| Prepare 20-lineup DK entries export | 9.432 s | 0.049 s | Exact CSV bytes preserved |
| Build labels for 176 saved DK players | 5.045 s | 0.025 s | Exact labels preserved |
| Route saved DK to preloaded FD workspace | Not asserted as a full-page baseline | 0.065 s | Complete DK state retained |
| Route back to DK | Not asserted as a full-page baseline | 0.069 s | Complete state and export bytes identical |

These are local measurements of the indicated functions. The navigation replay mocks persistence IO and does not claim to measure live-host scheduling, browser transport, network fetches or a cold cloud restore. The checkpoint profile measured current-state copying/restoring in roughly 0.05–0.10 seconds; that alone did not reproduce the user's long delay.

The saved DK portfolio and all 5,000 candidates survived the round trip, and its entries export remained byte-identical. Both workspaces were queued for backup. Tests also cover latest settings, isolation, invalid/duplicate events, closing active/inactive/last tabs and preservation of started-game clocks and export guards.

With detailed storage diagnostics enabled, Cloud storage connection now shows the last measured server-side slate-switch stages: capture, destination backup recovery, workspace restore and total routing. Those values help distinguish routing from a cold restore or later page rendering on the actual host.

The NBA regression runner now includes the workspace navigation/restore suites and new routing-priority tests so these guards run in CI. The frozen minutes candidate and holdout registry are unchanged.
