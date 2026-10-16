# DK Showdown production transforms — ready

Validated source state: `8cdb001bc3cb1e2b4630ca6bcc5bb63641d758a7`.

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

Final pre-install validation gate:

- Python syntax workflow: PASS on `8cdb001b`.
- DK Showdown field calibration workflow: PASS on `8cdb001b`.
- DK Engine Core workflow: PASS on `8cdb001b`.
- Regression test explicitly verifies that changing Min Uniques reselects only from the already-scored Contest Sim candidate pool.

Do not promote if any legacy marker survives:

- `auto_diversification_pct = 90.0`
- `max_shared_players = max(1, slot_count - 2)`
- `available_count = max(` from the legacy separate locked-portfolio branch.

The transformed live source must contain `locked_df=locked_df` in the post-sim selector call.

`main` is intentionally not targeted by this installation checkpoint.
