from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
needle = '''                st.success(f"Created {len(opponent_df):,} simulated FanDuel opponent lineups.")
'''
insert = '''                st.success(f"Created {len(opponent_df):,} simulated FanDuel opponent lineups.")
                # FanDuel Full Roster sanity diagnostics: show field construction
                # strength on every SIM so weak-field problems are visible before
                # trusting finish rates or ROI. FanDuel-only; DraftKings is untouched.
                if lineup_mode == "Full Roster":
                    _fd_sanity_user = st.session_state.get(fd_build_key)
                    _fd_field_proj = pd.to_numeric(opponent_df.get("ProjectedPoints"), errors="coerce").dropna()
                    _fd_field_salary = pd.to_numeric(opponent_df.get("Salary"), errors="coerce").dropna()
                    _fd_user_proj = (
                        pd.to_numeric(_fd_sanity_user.get("ProjectedPoints"), errors="coerce").dropna()
                        if isinstance(_fd_sanity_user, pd.DataFrame) and not _fd_sanity_user.empty
                        else pd.Series(dtype=float)
                    )
                    _fd_user_salary = (
                        pd.to_numeric(_fd_sanity_user.get("Salary"), errors="coerce").dropna()
                        if isinstance(_fd_sanity_user, pd.DataFrame) and not _fd_sanity_user.empty
                        else pd.Series(dtype=float)
                    )
                    st.write("### FanDuel Full Roster Field Sanity Check")
                    _fd_sanity_cols = st.columns(4)
                    _fd_sanity_cols[0].metric(
                        "Opponent avg projection",
                        f"{_fd_field_proj.mean():.2f}" if not _fd_field_proj.empty else "N/A",
                    )
                    _fd_sanity_cols[1].metric(
                        "My avg projection",
                        f"{_fd_user_proj.mean():.2f}" if not _fd_user_proj.empty else "N/A",
                    )
                    _fd_sanity_cols[2].metric(
                        "Opponent avg salary",
                        f"${_fd_field_salary.mean():,.0f}" if not _fd_field_salary.empty else "N/A",
                    )
                    _fd_sanity_cols[3].metric(
                        "My avg salary",
                        f"${_fd_user_salary.mean():,.0f}" if not _fd_user_salary.empty else "N/A",
                    )
                    if not _fd_field_proj.empty:
                        _fd_q = _fd_field_proj.quantile([0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
                        _fd_sanity_table = pd.DataFrame({
                            "Field metric": ["P10", "P25", "P50", "P75", "P90", "P95", "P99"],
                            "Projected points": [float(_fd_q.loc[q]) for q in [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]],
                        })
                        st.dataframe(_fd_sanity_table, use_container_width=True, hide_index=True)
                        if not _fd_user_proj.empty:
                            _fd_user_vs_field = float(np.mean([
                                np.mean(_fd_field_proj.to_numpy(dtype=float) <= score)
                                for score in _fd_user_proj.to_numpy(dtype=float)
                            ]))
                            st.caption(
                                f"Projection-only diagnostic: your generated lineups average the "
                                f"{100.0 * _fd_user_vs_field:.1f}th percentile versus the simulated opponent field. "
                                "This is not ROI; it isolates field-construction strength."
                            )
                    if not _fd_field_salary.empty:
                        _fd_near_cap = float((_fd_field_salary >= 59000).mean()) * 100.0
                        _fd_floor = float((_fd_field_salary >= 57000).mean()) * 100.0
                        st.caption(
                            f"Opponent salary usage: {_fd_near_cap:.1f}% use at least $59,000; "
                            f"{_fd_floor:.1f}% use at least $57,000."
                        )
'''
if needle not in text:
    raise SystemExit("FanDuel opponent success block not found; refusing to patch")
if "### FanDuel Full Roster Field Sanity Check" in text:
    print("FanDuel SIM sanity diagnostics already present")
    raise SystemExit(0)
text = text.replace(needle, insert, 1)
path.write_text(text, encoding="utf-8")
print("Added FanDuel Full Roster sanity diagnostics to SIM output")
