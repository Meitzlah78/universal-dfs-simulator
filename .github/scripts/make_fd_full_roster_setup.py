from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# Match the DK-style contest summary by adding a downloadable summary CSV after
# FanDuel contest comparison/ROI has been calculated.
fd_start = text.find('if platform == "FanDuel":')
if fd_start == -1:
    raise SystemExit("FanDuel branch not found")

old_heading = 'st.write("### FanDuel Contest Sim + ROI")'
if old_heading in text[fd_start:]:
    before = text[:fd_start]
    after = text[fd_start:].replace(old_heading, 'st.write("### FanDuel Contest Summary")', 1)
    text = before + after

anchor = '''                                st.caption("Uses the supplied Hail Mary payout ladder through 65,000th place. Representative-field ranks are scaled to the full contest field.")\n'''
if anchor not in text[fd_start:]:
    raise SystemExit("FanDuel ROI summary anchor not found")

addition = anchor + '''                                _fd_summary_download = pd.DataFrame([{\n                                    "Contest": _fd_selected.get("name", "Selected FanDuel contest"),\n                                    "Contest ID": _fd_selected.get("id", ""),\n                                    "Field Size": _fd_full_field,\n                                    "My Entries": _fd_my_entries,\n                                    "Entry Fee ($)": float(_fd_fee),\n                                    "Total Entry Fees ($)": round(_fd_total_fees, 2),\n                                    "Expected Winnings ($)": round(_fd_expected_winnings, 2),\n                                    "Expected Profit ($)": round(_fd_expected_profit, 2),\n                                    "Expected ROI (%)": round(_fd_expected_roi, 2),\n                                }])\n                                st.download_button(\n                                    "DOWNLOAD CONTEST SUMMARY",\n                                    data=_fd_summary_download.to_csv(index=False).encode("utf-8"),\n                                    file_name=f"fanduel_{lineup_mode.replace(' ', '_').lower()}_contest_summary.csv",\n                                    mime="text/csv",\n                                    use_container_width=True,\n                                    key="fd_contest_summary_download_" + lineup_mode.replace(" ", "_").lower(),\n                                )\n'''
text = text.replace(anchor, addition, 1)

path.write_text(text, encoding="utf-8")
