# DK Showdown production transforms — ready

Validated source state: `cce6dc631736da8c01e3773d1b0e83a3f66e82fc`.

Permanent installation order on this safety branch:

1. Run `.github/scripts/install_dk_exhaustive_build.py` against `dfs_app.py`.
2. Run `.github/scripts/install_dk_post_sim_diversification.py` against the transformed `dfs_app.py`.
3. Compile `dfs_app.py`, `dk_showdown_exhaustive.py`, `dk_showdown_build.py`, and `dk_portfolio_selection.py`.
4. Run the DK engine core validation suite before promoting the transformed app.

Required live behavior after installation:

- Build uses exhaustive legal Showdown screening and retains 5,000 competitive candidates.
- Candidate generation does not impose Min Uniques or automatic portfolio diversification.
- Contest Sim scores the candidate pool before portfolio diversification.
- Diversification happens after Contest Sim with Portfolio or explicit Min Uniques mode.
- Manual Max Exposure and Captain Max constraints are authoritative post-sim constraints.
- Locked lineups are retained, count toward exposure, and new selections must satisfy Min Uniques relative to locks.
- No hidden 90% exposure ceiling.
- No hidden two-unique overlap rule.
- Changing post-sim diversification reselects from already-simulated results rather than rebuilding candidates or the field.

Do not promote if either legacy marker survives:

- `auto_diversification_pct = 90.0`
- `max_shared_players = max(1, slot_count - 2)`

`main` is intentionally not targeted by this installation checkpoint.
