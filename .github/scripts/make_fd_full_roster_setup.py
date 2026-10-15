from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# Use the exact payout ladder supplied for the $45K Sun NFL Hail Mary contest.
needle = '''                                _fd_roi_cols = st.columns(5)
                                _fd_roi_cols[0].metric("Entries", f"{_fd_my_entries}")
                                _fd_roi_cols[1].metric("Entry Fees", f"${_fd_total_fees:,.2f}")
                                _fd_roi_cols[2].metric("Expected Winnings", "Pending payouts")
                                _fd_roi_cols[3].metric("Expected Profit", "Pending payouts")
                                _fd_roi_cols[4].metric("Expected ROI", "Pending payouts")
                                if not _fd_selected.get("prize_summary"):
                                    st.caption("Exact FanDuel winnings and ROI require the contest payout ladder. The app will not invent payouts when FanDuel does not expose them.")
'''
replacement = '''                                _fd_roi_cols = st.columns(5)
                                _fd_roi_cols[0].metric("Entries", f"{_fd_my_entries}")
                                _fd_roi_cols[1].metric("Entry Fees", f"${_fd_total_fees:,.2f}")
                                _fd_contest_name = str(_fd_selected.get("name", ""))
                                if "45K Sun NFL Hail Mary" in _fd_contest_name:
                                    _fd_payout_tiers = [
                                        (1, 1, 2000.0), (2, 2, 1000.0), (3, 3, 750.0),
                                        (4, 4, 500.0), (5, 5, 300.0), (6, 6, 200.0),
                                        (7, 7, 150.0), (8, 8, 125.0), (9, 10, 100.0),
                                        (11, 12, 75.0), (13, 15, 50.0), (16, 20, 30.0),
                                        (21, 25, 20.0), (26, 30, 15.0), (31, 40, 10.0),
                                        (41, 50, 7.50), (51, 75, 5.0), (76, 100, 4.0),
                                        (101, 150, 3.0), (151, 300, 2.0), (301, 600, 1.50),
                                        (601, 1000, 1.25), (1001, 3000, 1.0),
                                        (3001, 7500, 0.80), (7501, 15000, 0.70),
                                        (15001, 30000, 0.60), (30001, 65000, 0.50),
                                    ]
                                    _fd_full_field = int(_fd_field_label or 65000)
                                    _fd_rep_field = max(len(scores), 1)
                                    _fd_scaled_ranks = 1 + np.floor(
                                        np.maximum(pd.to_numeric(compared["FieldRank"], errors="coerce").fillna(_fd_rep_field).to_numpy(dtype=float) - 1.0, 0.0)
                                        * max(_fd_full_field - 1, 0) / max(_fd_rep_field - 1, 1)
                                    ).astype(int)
                                    _fd_scaled_ranks = np.clip(_fd_scaled_ranks, 1, max(_fd_full_field, 1))
                                    def _fd_prize_for_rank(rank):
                                        for lo, hi, prize in _fd_payout_tiers:
                                            if lo <= int(rank) <= hi:
                                                return float(prize)
                                        return 0.0
                                    compared["Estimated Full Field Rank"] = _fd_scaled_ranks
                                    compared["Expected Prize ($)"] = [_fd_prize_for_rank(r) for r in _fd_scaled_ranks]
                                    compared["Expected Net ($)"] = compared["Expected Prize ($)"] - float(_fd_fee)
                                    compared["Expected ROI (%)"] = 100.0 * compared["Expected Net ($)"] / max(float(_fd_fee), 0.01)
                                    _fd_entry_count = min(_fd_my_entries, len(compared))
                                    _fd_entry_pool = compared.nlargest(_fd_entry_count, "ContestScore") if _fd_entry_count > 0 else compared.iloc[0:0]
                                    _fd_expected_winnings = float(_fd_entry_pool["Expected Prize ($)"].sum())
                                    _fd_expected_profit = _fd_expected_winnings - _fd_total_fees
                                    _fd_expected_roi = 100.0 * _fd_expected_profit / max(_fd_total_fees, 0.01)
                                    _fd_roi_cols[2].metric("Expected Winnings", f"${_fd_expected_winnings:,.2f}")
                                    _fd_roi_cols[3].metric("Expected Profit", f"${_fd_expected_profit:,.2f}")
                                    _fd_roi_cols[4].metric("Expected ROI", f"{_fd_expected_roi:,.1f}%")
                                    st.caption("Uses the supplied Hail Mary payout ladder through 65,000th place. Representative-field ranks are scaled to the full contest field.")
                                else:
                                    _fd_roi_cols[2].metric("Expected Winnings", "Pending payouts")
                                    _fd_roi_cols[3].metric("Expected Profit", "Pending payouts")
                                    _fd_roi_cols[4].metric("Expected ROI", "Pending payouts")
                                    if not _fd_selected.get("prize_summary"):
                                        st.caption("Exact FanDuel winnings and ROI require the contest payout ladder. The app will not invent payouts when FanDuel does not expose them.")
'''
if needle not in text:
    raise SystemExit("FanDuel ROI display block not found")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
