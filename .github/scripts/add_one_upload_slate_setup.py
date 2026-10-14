from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")


def replace_required(old, new, label):
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch anchor not found: {label}")
    text = text.replace(old, new, 1)


replace_required(
'''    with build_cols[2]:
        st.write("### Run")
        fd_run_all_clicked = st.button(
            "RUN SIM → BUILD → CONTEST SIM",
            type="primary",
            use_container_width=True,
            key="fd_run_all_" + lineup_mode.replace(" ", "_").lower(),
            help="Run all three FanDuel steps in order, with a progress bar."
        )
        fd_sim_clicked = fd_run_all_clicked
        fd_build_clicked = fd_run_all_clicked
        fd_contest_clicked = fd_run_all_clicked
''',
'''    with build_cols[2]:
        st.write("### Run")
        _fd_run_cols = st.columns(3)
        with _fd_run_cols[0]:
            fd_sim_button = st.button("SIM", type="primary", use_container_width=True, key="fd_sim_" + lineup_mode.replace(" ", "_").lower())
        with _fd_run_cols[1]:
            fd_build_button = st.button("BUILD", use_container_width=True, key="fd_build_" + lineup_mode.replace(" ", "_").lower())
        with _fd_run_cols[2]:
            fd_contest_button = st.button("CONTEST SIM", use_container_width=True, key="fd_contest_" + lineup_mode.replace(" ", "_").lower())
        fd_run_all_clicked = fd_sim_button or fd_build_button or fd_contest_button
        fd_sim_clicked = fd_run_all_clicked
        fd_build_clicked = fd_run_all_clicked
        fd_contest_clicked = fd_run_all_clicked
''',
"FanDuel SIM BUILD CONTEST SIM buttons",
)

replace_required(
'''        with build_cols[2]:
            st.write("### Run")
            classic_run_all = st.button("SIM", type="primary", use_container_width=True, key="dk_classic_run_all")
''',
'''        with build_cols[2]:
            st.write("### Run")
            _classic_run_cols = st.columns(3)
            with _classic_run_cols[0]:
                _classic_sim_button = st.button("SIM", type="primary", use_container_width=True, key="dk_classic_sim")
            with _classic_run_cols[1]:
                _classic_build_button = st.button("BUILD", use_container_width=True, key="dk_classic_build")
            with _classic_run_cols[2]:
                _classic_contest_button = st.button("CONTEST SIM", use_container_width=True, key="dk_classic_contest")
            classic_run_all = _classic_sim_button or _classic_build_button or _classic_contest_button
''',
"DraftKings Classic SIM BUILD CONTEST SIM buttons",
)

replace_required(
'''                    st.metric("Simulated opponent lineups", f"{len(contest_field_df):,}")
                    # Field ownership is already shown in the Player Pool.
''',
'''                    st.metric("Simulated opponent lineups", f"{len(contest_field_df):,}")
                    if all(c in user_lineups.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                        _classic_sanity = pd.DataFrame([{
                            "Top 1%": round(100 * float(user_lineups["Top1"].mean()), 2),
                            "Top 5%": round(100 * float(user_lineups["Top5"].mean()), 2),
                            "Top 10%": round(100 * float(user_lineups["Top10"].mean()), 2),
                            "Cash %": round(100 * float(user_lineups["CashRate"].mean()), 2),
                        }])
                        st.write("### Field Sanity Check")
                        st.dataframe(_classic_sanity, use_container_width=True, hide_index=True)
                    # Field ownership is already shown in the Player Pool.
''',
"DraftKings Classic field sanity",
)

replace_required(
'''                        st.dataframe(compared, use_container_width=True, hide_index=True)
                        # Keep the contest results area consistent with DraftKings Classic and Showdown.
''',
'''                        st.dataframe(compared, use_container_width=True, hide_index=True)
                        if all(c in compared.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                            _fd_sanity = pd.DataFrame([{
                                "Top 1%": round(100 * float(compared["Top1"].mean()), 2),
                                "Top 5%": round(100 * float(compared["Top5"].mean()), 2),
                                "Top 10%": round(100 * float(compared["Top10"].mean()), 2),
                                "Cash %": round(100 * float(compared["CashRate"].mean()), 2),
                            }])
                            st.write("### Field Sanity Check")
                            st.dataframe(_fd_sanity, use_container_width=True, hide_index=True)
                        # Keep the contest results area consistent with DraftKings Classic and Showdown.
''',
"FanDuel field sanity",
)

path.write_text(text, encoding="utf-8")
print("Applied paired workflow controls and field sanity summaries")
# trigger paired-format patch 2026-10-14
