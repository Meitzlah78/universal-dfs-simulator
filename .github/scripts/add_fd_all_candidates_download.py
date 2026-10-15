from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

if 'key="download_fd_all_candidate_lineups"' in text:
    print("All-candidates download already present.")
    raise SystemExit(0)

# Insert directly before fd_display_columns, using that line's exact indentation.
marker = "fd_display_columns ="
pos = text.find(marker)
if pos < 0:
    raise SystemExit("Could not find FanDuel display/export insertion point")

line_start = text.rfind("\n", 0, pos) + 1
indent = text[line_start:pos]

lines = [
    'if lineup_mode == "Full Roster" and isinstance(compared, pd.DataFrame) and not compared.empty:',
    '    _fd_all_candidates_export = compared.copy()',
    '    st.download_button(',
    '        "DOWNLOAD ALL CANDIDATE LINEUPS",',
    '        data=_fd_all_candidates_export.to_csv(index=False).encode("utf-8"),',
    '        file_name="fanduel_all_candidate_lineups.csv",',
    '        mime="text/csv",',
    '        key="download_fd_all_candidate_lineups",',
    '        use_container_width=True,',
    '    )',
    '',
]
block = "\n".join(indent + line if line else "" for line in lines)
text = text[:line_start] + block + text[line_start:]
path.write_text(text)
print("Added FanDuel Full Roster all-candidate CSV download.")
