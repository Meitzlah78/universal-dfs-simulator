# Three workspaces across all four formats

The shared format selector and projection/injury refresh control stay above three tabs:

1. **Contests**: universal entry CSV upload, format-specific entry selection, field capacity, saved contest metadata, and payout controls. Historical standings imports, post-game reports and the ROI tracker live in collapsed sections here.
2. **Roster & Projections**: source status and uploads, injuries, player pool, exposure controls, weather, projection downloads and collapsed diagnostics/accuracy reports.
3. **Build**: salary and simulation-diversity settings, workflow progress, candidates, opponent samples, ranking, portfolio ROI and existing-entry exports.

This is a layout reorganization, not a change to projection formulas, simulation counts, roster rules, or export identifiers. All pre-existing function bodies and widget keys remain intact. Streamlit tabs render eagerly; tabs reduce visible clutter, not CPU/network work. The shared variables still execute in their original order.

`simmah_saved_contests.py` stores only reusable contest metadata, scoped by exact format plus contest ID. Restore never transfers entry IDs or your entry count between contests; the matching entries CSV must be uploaded before saved metadata can be applied. Current reserved-entry export checks remain unchanged. Built-in records include verified FD Hail Mary/Pooch Punt and DK DAL–GB/HOU–JAX contests. Classic's existing preset selector also appears in Contests.

New saved metadata lives in `data/saved_contests_local.json` on the current server. The Contests tab offers JSON backup/restore for redeploys. It does not pretend local hosting storage survives every deployment, or treat a past contest's payout family as a new contest's verified schedule.

Validation covers tab routing, preserved entry-widget keys, exact-ID/format restore, preserved current entry count, deduplication, invalid payouts and backup round-trip. Static AST comparison verifies every original function body is unchanged. Live Streamlit visual testing is still required after deployment.

## Reference dashboard styling

The October 19 reference image guides the navy/teal theme, SIMMAH wordmark, compact player grid and permanent right-hand build rail. The three requested task tabs remain in the main column. Native Streamlit widgets are retained for keyboard access and existing event handling. No sample player values, ownership estimates, team badges, simulated completion states or nonfunctional mock controls are introduced.

`simmah_ui.py` supplies presentation only; `.streamlit/config.toml` sets the native dark theme so dataframe cells match the surrounding interface. Editable tables default to a concise column set with a Show all player columns switch. Hiding display columns does not remove those fields from the editor's returned dataframe or downstream calculations.

Real Streamlit AppTest smoke checks render all four format shells with external requests disabled, and confirm hidden editor columns are retained. These checks validate rendering and data preservation, not browser screenshot equivalence or a live slate build. The former fixed refresh strip is now in normal header flow, avoiding overlap with navigation on smaller screens.
