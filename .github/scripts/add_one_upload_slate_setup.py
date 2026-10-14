from pathlib import Path

p = Path('dfs_app.py')
s = p.read_text()

# Keep this patch strictly inside DraftKings Classic. Showdown is not changed.
anchor = '''        st.caption("Choose your DraftKings Classic stack rules before pressing BUILD.")\n\n        with build_cols[2]:'''
insert = '''        st.caption("Choose your DraftKings Classic stack rules before pressing BUILD.")

        # Real DraftKings Classic main-slate contests supplied by the user.
        # Each payout tuple is (first_place, last_place, prize_dollars).
        CLASSIC_CONTESTS = {
            "NFL $4K Dime Package [Just $0.10!]": {"entry": 0.10, "field": 47500, "max_entries": 20, "prize_pool": 4000, "payouts": [(1,1,200),(2,2,150),(3,3,100),(4,4,75),(5,5,60),(6,6,50),(7,7,40),(8,8,30),(9,9,25),(10,10,20),(11,15,15),(16,20,10),(21,25,8),(26,30,6),(31,40,5),(41,50,4),(51,65,3),(66,85,2),(86,110,1.5),(111,155,1),(156,275,.75),(276,585,.50),(586,1385,.40),(1386,3670,.30),(3671,11405,.20)]},
            "NFL $15K Quarter Jukebox [Just $0.25!]": {"entry": .25, "field": 71300, "max_entries": 20, "prize_pool": 15000, "payouts": [(1,1,750),(2,2,500),(3,3,300),(4,4,200),(5,5,150),(6,7,100),(8,10,75),(11,15,50),(16,20,40),(21,25,30),(26,30,25),(31,40,20),(41,50,15),(51,65,10),(66,85,8),(86,110,6),(111,140,5),(141,180,4),(181,240,3),(241,425,2),(426,845,1.5),(846,2105,1),(2106,5635,.75),(5636,17120,.50)]},
            "NFL $175K mini-MAX [150 Entry Max]": {"entry": .50, "field": 416100, "max_entries": 150, "prize_pool": 175000, "payouts": [(1,1,20000),(2,2,7500),(3,3,3000),(4,4,2000),(5,5,1500),(6,6,1000),(7,8,750),(9,10,600),(11,12,500),(13,15,400),(16,19,300),(20,24,250),(25,30,200),(31,40,150),(41,50,100),(51,65,75),(66,85,60),(86,110,50),(111,140,40),(141,180,30),(181,230,25),(231,290,20),(291,370,15),(371,490,10),(491,640,8),(641,840,6),(841,1615,5),(1616,3120,4),(3121,6270,3),(6271,14035,2),(14036,29015,1.5),(29016,87395,1)]},
            "NFL $4K Mini First Down": {"entry": 1, "field": 4756, "max_entries": 20, "prize_pool": 4000, "payouts": [(1,1,400),(2,2,200),(3,3,150),(4,4,100),(5,5,80),(6,6,70),(7,7,60),(8,8,50),(9,10,40),(11,15,30),(16,20,20),(21,25,15),(26,35,10),(36,50,8),(51,80,6),(81,150,4),(151,300,3),(301,601,2),(602,1103,1.5)]},
            "NFL $2.75M Fantasy Football Millionaire": {"entry": 20, "field": 161700, "max_entries": 150, "prize_pool": 2750000, "payouts": [(1,1,1000000),(2,2,100000),(3,3,50000),(4,4,25000),(5,5,15000),(6,6,10000),(7,8,7000),(9,10,5000),(11,15,3000),(16,20,2000),(21,30,1500),(31,45,1000),(46,65,700),(66,95,500),(96,135,400),(136,195,300),(196,315,200),(316,515,150),(516,1025,100),(1026,2425,70),(2426,5925,50),(5926,14425,40),(14426,37425,30)]},
            "NFL $600K Play-Action [20 Entry Max]": {"entry": 3, "field": 237800, "max_entries": 20, "prize_pool": 600000, "payouts": [(1,1,50000),(2,2,25000),(3,3,15000),(4,4,10000),(5,5,7500),(6,6,5000),(7,8,3000),(9,10,2000),(11,15,1500),(16,20,1000),(21,30,750),(31,40,500),(41,50,300),(51,75,200),(76,100,150),(101,150,100),(151,250,75),(251,350,60),(351,550,50),(551,750,40),(751,1000,30),(1001,1500,20),(1501,2500,15),(2501,4000,12),(4001,6500,10),(6501,10000,9),(10001,15000,8),(15001,25000,7),(25001,39000,6),(39001,59650,5)]},
            "NFL $400K Flea Flicker [$50K to 1st]": {"entry": 5, "field": 95100, "max_entries": 150, "prize_pool": 400000, "payouts": [(1,1,50000),(2,2,25000),(3,3,15000),(4,4,10000),(5,5,7000),(6,6,5000),(7,8,3000),(9,10,2000),(11,15,1500),(16,20,1000),(21,25,700),(26,30,500),(31,40,300),(41,50,200),(51,75,150),(76,100,100),(101,150,75),(151,250,50),(251,450,35),(451,850,25),(851,1600,20),(1601,3100,15),(3101,6100,12),(6101,12400,10),(12401,23150,8)]},
            "NFL $100K First Down [20 Entry Max]": {"entry": 1, "field": 118900, "max_entries": 20, "prize_pool": 100000, "payouts": [(1,1,5000),(2,2,2500),(3,3,1500),(4,4,1000),(5,5,750),(6,7,600),(8,10,500),(11,14,400),(15,19,300),(20,25,250),(26,35,200),(36,45,150),(46,60,100),(61,80,75),(81,105,60),(106,135,50),(136,175,40),(176,225,30),(226,285,25),(286,360,20),(361,460,15),(461,610,10),(611,800,8),(801,1085,6),(1086,1665,5),(1666,3005,4),(3006,6110,3),(6111,13242,2),(13243,32096,1.5)]},
            "NFL $50K MEGA mini-MAX [150 Entry Max]": {"entry": 2, "field": 29700, "max_entries": 150, "prize_pool": 50000, "payouts": [(1,1,5000),(2,2,2500),(3,3,1000),(4,4,600),(5,5,500),(6,6,400),(7,8,300),(9,10,250),(11,14,200),(15,20,150),(21,30,100),(31,40,75),(41,55,60),(56,70,50),(71,90,40),(91,115,30),(116,145,25),(146,185,20),(186,235,15),(236,385,10),(386,700,8),(701,1325,6),(1326,2525,5),(2526,6570,4)]},
            "NFL $40K Front Four [20 Entry Max]": {"entry": 4, "field": 11800, "max_entries": 20, "prize_pool": 40000, "payouts": [(1,1,4000),(2,2,2000),(3,3,1500),(4,4,1000),(5,5,750),(6,6,600),(7,8,500),(9,10,400),(11,12,300),(13,14,250),(15,16,200),(17,21,150),(22,26,100),(27,31,75),(32,36,60),(37,46,50),(47,56,40),(57,71,30),(72,96,25),(97,151,20),(152,291,15),(292,661,10),(662,1396,8),(1397,3091,6)]},
            "NFL $20K Safety [20 Entry Max]": {"entry": 2, "field": 11800, "max_entries": 20, "prize_pool": 20000, "payouts": [(1,1,1000),(2,2,600),(3,3,400),(4,4,300),(5,5,250),(6,7,200),(8,10,150),(11,15,100),(16,20,75),(21,30,60),(31,40,50),(41,50,40),(51,65,30),(66,85,25),(86,110,20),(111,140,15),(141,190,10),(191,295,8),(296,515,6),(516,930,5),(931,1680,4),(1681,3210,3)]},
        }
        classic_contest_name = st.selectbox(
            "Classic contest for CONTEST SIM", list(CLASSIC_CONTESTS),
            key="dk_classic_contest_name"
        )
        classic_contest = CLASSIC_CONTESTS[classic_contest_name]
        classic_entry_count = st.number_input(
            "My entries in this Classic contest", min_value=1,
            max_value=int(classic_contest["max_entries"]),
            value=int(classic_contest["max_entries"]), step=1,
            key="dk_classic_contest_entry_count"
        )
        st.caption(
            f"${classic_contest['entry']:.2f} entry · {classic_contest['field']:,} max field · "
            f"${classic_contest['prize_pool']:,.0f} prizes · {classic_contest['max_entries']} entry max"
        )

        with build_cols[2]:'''
if anchor not in s:
    raise SystemExit('Classic contest selector anchor not found')
s = s.replace(anchor, insert, 1)

# Make the three Classic buttons do their own jobs. BUILD refreshes SIM first;
# CONTEST SIM uses the saved build and does not rebuild it.
s = s.replace('''        if classic_run_all:\n            classic_workflow_status = st.empty()''', '''        if _classic_sim_button or _classic_build_button:\n            classic_workflow_status = st.empty()''', 1)
s = s.replace('''        build_clicked = classic_run_all\n''', '''        build_clicked = _classic_build_button\n''', 1)
s = s.replace('''        if classic_run_all and platform == "DraftKings" and lineup_mode == "Classic":''', '''        if _classic_contest_button and platform == "DraftKings" and lineup_mode == "Classic":''', 1)

# Score the Classic comparison against the selected real contest payout ladder.
score_anchor = '''                        user_lineups = add_field_ranking_metrics(user_lineups, opponent_scores)\n                    st.session_state["classic_contest_field_df"] = contest_field_df'''
score_insert = '''                        user_lineups = add_field_ranking_metrics(user_lineups, opponent_scores)
                        # Convert representative-field percentile to the selected contest's
                        # full-field rank, then apply its exact payout ladder.
                        full_field_size = int(classic_contest["field"])
                        user_lineups["Estimated Full Field Rank"] = user_lineups["FieldPercentile"].apply(
                            lambda pct: max(1, min(full_field_size, int(np.ceil((1.0 - float(pct) / 100.0) * full_field_size))))
                        )
                        def _classic_prize(rank):
                            for first, last, prize in classic_contest["payouts"]:
                                if int(first) <= int(rank) <= int(last):
                                    return float(prize)
                            return 0.0
                        user_lineups["Expected Prize ($)"] = user_lineups["Estimated Full Field Rank"].map(_classic_prize)
                        user_lineups["Entry Fee ($)"] = float(classic_contest["entry"])
                        user_lineups["Expected Net ($)"] = user_lineups["Expected Prize ($)"] - float(classic_contest["entry"])
                        user_lineups["Expected ROI (%)"] = 100.0 * user_lineups["Expected Net ($)"] / float(classic_contest["entry"])
                        # Contest entries are the best requested number of lineups by the
                        # existing ContestScore metric (fallback to AvgPercentile).
                        rank_col = "ContestScore" if "ContestScore" in user_lineups.columns else "AvgPercentile"
                        contest_entries = user_lineups.sort_values(rank_col, ascending=False).head(int(classic_entry_count)).copy()
                        st.session_state["classic_contest_entries_df"] = contest_entries
                    st.session_state["classic_contest_field_df"] = contest_field_df'''
if score_anchor not in s:
    raise SystemExit('Classic scoring anchor not found')
s = s.replace(score_anchor, score_insert, 1)

# Add the ROI summary immediately above Field Sanity Check.
summary_anchor = '''                    st.metric("Simulated opponent lineups", f"{len(contest_field_df):,}")\n                    if all(c in user_lineups.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):'''
summary_insert = '''                    st.metric("Simulated opponent lineups", f"{len(contest_field_df):,}")
                    contest_entries = st.session_state.get("classic_contest_entries_df", pd.DataFrame())
                    if isinstance(contest_entries, pd.DataFrame) and not contest_entries.empty:
                        total_fees = float(classic_contest["entry"]) * len(contest_entries)
                        expected_winnings = float(contest_entries["Expected Prize ($)"].sum())
                        expected_profit = expected_winnings - total_fees
                        expected_roi = (100.0 * expected_profit / total_fees) if total_fees > 0 else 0.0
                        st.write("### Classic Contest Sim + ROI")
                        st.caption(f"{classic_contest_name} · full field {classic_contest['field']:,} · {len(contest_entries)} of your entries")
                        _roi_cols = st.columns(5)
                        _roi_cols[0].metric("Entries", f"{len(contest_entries)}")
                        _roi_cols[1].metric("Entry Fees", f"${total_fees:,.2f}")
                        _roi_cols[2].metric("Expected Winnings", f"${expected_winnings:,.2f}")
                        _roi_cols[3].metric("Expected Profit", f"${expected_profit:,.2f}")
                        _roi_cols[4].metric("Expected ROI", f"{expected_roi:,.1f}%")
                        st.dataframe(contest_entries, use_container_width=True, hide_index=True)
                    if all(c in user_lineups.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):'''
if summary_anchor not in s:
    raise SystemExit('Classic ROI summary anchor not found')
s = s.replace(summary_anchor, summary_insert, 1)

# Do not rerun after CONTEST SIM; keep its results visible. SIM/BUILD may rerun
# once so the Player Pool refreshes with the newest simulation/build data.
s = s.replace('''        if classic_run_all:\n            st.rerun()\n        st.stop()''', '''        if _classic_sim_button or _classic_build_button:\n            st.rerun()\n        st.stop()''', 1)

p.write_text(s)
print('Patched DraftKings Classic contest library, separate buttons, and ROI output; Showdown untouched.')
