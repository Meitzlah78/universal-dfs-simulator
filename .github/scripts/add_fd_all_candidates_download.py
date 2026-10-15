from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()

# Insert immediately before the existing FanDuel final-portfolio download when possible.
needles = [
    'st.download_button(\n                    "Download FanDuel lineups CSV"',
    'st.download_button(\n                    label="Download FanDuel lineups CSV"',
    'st.download_button(\n                "Download FanDuel lineups CSV"',
    'st.download_button(\n                label="Download FanDuel lineups CSV"',
]

insert = '''if lineup_mode == "Full Roster" and isinstance(compared, pd.DataFrame) and not compared.empty:\n                    _fd_all_candidates_export = compared.copy()\n                    st.download_button(\n                        "DOWNLOAD ALL CANDIDATE LINEUPS",\n                        data=_fd_all_candidates_export.to_csv(index=False).encode("utf-8"),\n                        file_name="fanduel_all_candidate_lineups.csv",\n                        mime="text/csv",\n                        key="download_fd_all_candidate_lineups",\n                        use_container_width=True,\n                    )\n                '''

if 'key="download_fd_all_candidate_lineups"' in text:
    print('All-candidates download already present.')
else:
    for needle in needles:
        pos = text.find(needle)
        if pos >= 0:
            line_start = text.rfind('\n', 0, pos) + 1
            indent = text[line_start:pos]
            block = insert.replace('\n', '\n' + indent)
            text = text[:line_start] + indent + block + text[line_start:]
            break
    else:
        # More robust fallback: place it immediately before the FanDuel display/export
        # section marker if the button label has changed.
        marker = 'fd_display_columns ='
        pos = text.find(marker)
        if pos < 0:
            raise SystemExit('Could not find FanDuel export/display insertion point')
        line_start = text.rfind('\n', 0, pos) + 1
        indent = text[line_start:pos]
        block = insert.replace('\n', '\n' + indent)
        text = text[:line_start] + indent + block + text[line_start:]

path.write_text(text)
print('Added FanDuel Full Roster all-candidate CSV download.')
