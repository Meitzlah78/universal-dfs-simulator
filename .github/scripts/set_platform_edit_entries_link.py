from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')
old = '''# Quick link to DraftKings lineup upload.\ntop_buttons = st.columns(2)\nwith top_buttons[0]:\n    st.link_button(\n        "EDIT ENTRIES",\n        "https://www.draftkings.com/entry/upload",\n        use_container_width=True,\n    )\n'''
new = '''# Quick entry-management link follows the selected DFS site.\n_top_platform = str(st.session_state.get("dfs_platform", "DraftKings")).strip()\n_edit_entries_url = (\n    "https://www.fanduel.com/upcoming"\n    if _top_platform.casefold() == "fanduel"\n    else "https://www.draftkings.com/entry/upload"\n)\ntop_buttons = st.columns(2)\nwith top_buttons[0]:\n    st.link_button(\n        "EDIT ENTRIES",\n        _edit_entries_url,\n        use_container_width=True,\n    )\n'''
if old not in text:
    if new in text:
        print('platform-aware EDIT ENTRIES link already present')
        raise SystemExit(0)
    raise SystemExit('target EDIT ENTRIES block not found')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('made EDIT ENTRIES platform-aware')
