from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
needle = '''                        if all(c in compared.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                            _fd_sanity = pd.DataFrame([{
'''
insert = '''                        if lineup_mode == "Full Roster":
                            _fd_selected = st.session_state.get("selected_fd_contest") or {}
                            _fd_fee = _fd_selected.get("entry_fee")
                            _fd_my_entries = int(_fd_selected.get("your_entries") or 0)
                            if _fd_selected and _fd_fee is not None and _fd_my_entries > 0:
                                _fd_total_fees = float(_fd_fee) * _fd_my_entries
                                st.write("### FanDuel Contest Sim + ROI")
                                _fd_field_label = _fd_selected.get("field_size") or _fd_selected.get("current_entries")
                                _fd_caption = f"{_fd_selected.get('name', 'Selected FanDuel contest')} · {_fd_my_entries} of your entries"
                                if _fd_field_label:
                                    _fd_caption += f" · full field {int(_fd_field_label):,}"
                                st.caption(_fd_caption)
                                _fd_roi_cols = st.columns(5)
                                _fd_roi_cols[0].metric("Entries", f"{_fd_my_entries}")
                                _fd_roi_cols[1].metric("Entry Fees", f"${_fd_total_fees:,.2f}")
                                _fd_roi_cols[2].metric("Expected Winnings", "Pending payouts")
                                _fd_roi_cols[3].metric("Expected Profit", "Pending payouts")
                                _fd_roi_cols[4].metric("Expected ROI", "Pending payouts")
                                if not _fd_selected.get("prize_summary"):
                                    st.caption("Exact FanDuel winnings and ROI require the contest payout ladder. The app will not invent payouts when FanDuel does not expose them.")
                        if all(c in compared.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                            _fd_sanity = pd.DataFrame([{
'''
if needle not in text:
    raise SystemExit("FanDuel contest results block not found")
text = text.replace(needle, insert, 1)
path.write_text(text, encoding="utf-8")
