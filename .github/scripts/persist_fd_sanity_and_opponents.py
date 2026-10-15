from pathlib import Path

path = Path("dfs_app.py")
s = path.read_text(encoding="utf-8")
anchor = '''        fd_rank_label = st.selectbox(
            "Rank lineups by", list(PORTFOLIO_METRICS.keys()),
'''
if anchor not in s:
    raise SystemExit("FanDuel ranking anchor not found")
if "Persistent FanDuel Full Roster sanity check" in s:
    print("Persistent FanDuel diagnostics already present")
    raise SystemExit(0)
block = '''        # Persistent FanDuel Full Roster sanity check and opponent lineup viewer.
        # Read from session state so these remain visible after SIM triggers st.rerun().
        if lineup_mode == "Full Roster":
            _fd_field_key = "fd_contest_field_" + lineup_mode.replace(" ", "_").lower()
            _fd_persist_field = st.session_state.get(_fd_field_key)
            if isinstance(_fd_persist_field, pd.DataFrame) and not _fd_persist_field.empty:
                _fd_field_proj = pd.to_numeric(_fd_persist_field.get("ProjectedPoints"), errors="coerce").dropna()
                _fd_field_salary = pd.to_numeric(_fd_persist_field.get("Salary"), errors="coerce").dropna()
                _fd_my_proj = pd.to_numeric(fd_rank_source.get("ProjectedPoints"), errors="coerce").dropna()
                _fd_my_salary = pd.to_numeric(fd_rank_source.get("Salary"), errors="coerce").dropna()

                st.write("### FanDuel Full Roster Field Sanity Check")
                _fd_sc = st.columns(4)
                _fd_sc[0].metric("Opponent avg projection", f"{_fd_field_proj.mean():.2f}" if not _fd_field_proj.empty else "N/A")
                _fd_sc[1].metric("My avg projection", f"{_fd_my_proj.mean():.2f}" if not _fd_my_proj.empty else "N/A")
                _fd_sc[2].metric("Opponent avg salary", f"${_fd_field_salary.mean():,.0f}" if not _fd_field_salary.empty else "N/A")
                _fd_sc[3].metric("My avg salary", f"${_fd_my_salary.mean():,.0f}" if not _fd_my_salary.empty else "N/A")

                if not _fd_field_proj.empty:
                    _fd_q_levels = [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
                    _fd_q = _fd_field_proj.quantile(_fd_q_levels)
                    st.dataframe(pd.DataFrame({
                        "Opponent field": ["P10", "P25", "P50", "P75", "P90", "P95", "P99"],
                        "Projected points": [round(float(_fd_q.loc[q]), 2) for q in _fd_q_levels],
                    }), use_container_width=True, hide_index=True)
                    if not _fd_my_proj.empty:
                        _fd_field_values = _fd_field_proj.to_numpy(dtype=float)
                        _fd_my_percentiles = [float(np.mean(_fd_field_values <= x)) for x in _fd_my_proj.to_numpy(dtype=float)]
                        st.caption(
                            f"Projection-only diagnostic: your generated lineup pool averages the "
                            f"{100.0 * float(np.mean(_fd_my_percentiles)):.1f}th percentile versus the opponent field."
                        )
                if not _fd_field_salary.empty:
                    st.caption(
                        f"Opponent salary usage: {100.0 * float((_fd_field_salary >= 59000).mean()):.1f}% use at least $59,000; "
                        f"{100.0 * float((_fd_field_salary >= 57000).mean()):.1f}% use at least $57,000."
                    )

                with st.expander(f"Opponent Lineup Info — {len(_fd_persist_field):,} simulated entries", expanded=False):
                    _fd_opponent_show = _fd_persist_field.copy()
                    _fd_opponent_show["ProjectedPoints"] = pd.to_numeric(_fd_opponent_show.get("ProjectedPoints"), errors="coerce")
                    _fd_opponent_show["Salary"] = pd.to_numeric(_fd_opponent_show.get("Salary"), errors="coerce")
                    _fd_opponent_show = _fd_opponent_show.sort_values("ProjectedPoints", ascending=False, na_position="last")
                    st.caption("Showing the 100 highest-projected simulated opponent lineups. Download contains the full opponent field, including duplicates.")
                    st.dataframe(_fd_opponent_show.head(100), use_container_width=True, hide_index=True)
                    st.download_button(
                        "Download Full Opponent Field CSV",
                        data=_fd_opponent_show.to_csv(index=False).encode("utf-8"),
                        file_name="fanduel_full_roster_opponent_field.csv",
                        mime="text/csv",
                        key="fd_download_opponent_field_full_roster",
                    )
            else:
                st.caption("FanDuel field sanity and opponent lineup info will appear here after Contest SIM builds the opponent field.")

'''
s = s.replace(anchor, block + anchor, 1)
path.write_text(s, encoding="utf-8")
print("Added persistent FanDuel sanity and opponent lineup info")
