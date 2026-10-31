from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
old = '''        if st.button("FETCH DRAFTKINGS CONTEST DETAILS", key="fetch_dk_contest_details", use_container_width=True):
            try:
                _contest_id_for_api = str(_selected_dk_for_details["id"]).strip()
'''
new = '''        _fetch_dk_details_clicked = st.button(
            "FETCH DRAFTKINGS CONTEST DETAILS",
            key="fetch_dk_contest_details",
            use_container_width=True,
        )
        _selected_contest_id_for_payout = str(_selected_dk_for_details.get("id", "")).strip()
        _payout_needs_refresh = (
            bool(_selected_contest_id_for_payout)
            and (
                str(st.session_state.get("contest_payout_contest_id", "")) != _selected_contest_id_for_payout
                or not isinstance(st.session_state.get("contest_payout_schedule"), np.ndarray)
                or len(st.session_state.get("contest_payout_schedule", [])) == 0
            )
        )
        if _fetch_dk_details_clicked or _payout_needs_refresh:
            try:
                _contest_id_for_api = str(_selected_dk_for_details["id"]).strip()
'''
if new in text:
    print("DraftKings payout auto-fetch patch already applied.")
elif old not in text:
    raise SystemExit("Target DraftKings contest-details block was not found.")
else:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("DraftKings payout details now auto-fetch for newly selected contests.")
