from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

marker = '''    _saved_payouts = st.session_state.get("contest_payout_schedule")
'''

block = '''    # Verified payout ladder supplied from the DraftKings contest details for
    # NFL Showdown $4K Dime Package [Just $0.10!] (SEA @ DEN).
    # Match the exact contest name so this fallback cannot leak into another contest.
    _selected_dk_name = str(st.session_state.get("selected_dk_contest", {}).get("name", "")).strip()
    _selected_dk_id = str(st.session_state.get("selected_dk_contest", {}).get("id", "")).strip()
    if (
        _selected_dk_name == "NFL Showdown $4K Dime Package [Just $0.10!] (SEA @ DEN)"
        and str(st.session_state.get("contest_payout_contest_id", "")) != _selected_dk_id
    ):
        _sea_den_dime_ranges = [
            (1, 1, 200.00), (2, 2, 150.00), (3, 3, 100.00), (4, 4, 75.00),
            (5, 5, 60.00), (6, 6, 50.00), (7, 7, 40.00), (8, 8, 30.00),
            (9, 9, 25.00), (10, 10, 20.00), (11, 15, 15.00), (16, 20, 10.00),
            (21, 25, 8.00), (26, 30, 6.00), (31, 40, 5.00), (41, 50, 4.00),
            (51, 65, 3.00), (66, 85, 2.00), (86, 110, 1.50), (111, 155, 1.00),
            (156, 275, 0.75), (276, 585, 0.50), (586, 1385, 0.40),
            (1386, 3670, 0.30), (3671, 11405, 0.20),
        ]
        _sea_den_dime_schedule = np.zeros(11405, dtype=float)
        for _rank_start, _rank_end, _rank_prize in _sea_den_dime_ranges:
            _sea_den_dime_schedule[_rank_start - 1:_rank_end] = _rank_prize
        # The supplied payout ladder totals exactly $4,000.
        st.session_state["contest_payout_schedule"] = _sea_den_dime_schedule
        st.session_state["contest_payout_source_name"] = "Verified SEA @ DEN $4K Dime Package payout table"
        st.session_state["contest_payout_contest_id"] = _selected_dk_id
        st.session_state["contest_payout_auto_loaded"] = True

'''

if block in text:
    print("SEA/DEN Dime payout fallback already applied.")
elif marker in text:
    text = text.replace(marker, block + marker, 1)
    path.write_text(text, encoding="utf-8")
    print("Added verified SEA/DEN Dime payout fallback.")
else:
    raise SystemExit("Could not find payout summary marker")
