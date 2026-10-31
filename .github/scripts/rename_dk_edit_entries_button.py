from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
old = '''    st.link_button(\n        "CONTEST",\n        "https://www.draftkings.com/entry/upload",\n        use_container_width=True,\n    )'''
new = '''    st.link_button(\n        "EDIT ENTRIES",\n        "https://www.draftkings.com/entry/upload",\n        use_container_width=True,\n    )'''

if old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Renamed DraftKings contest button to EDIT ENTRIES.")
elif '"EDIT ENTRIES"' in text and 'https://www.draftkings.com/entry/upload' in text:
    print("DraftKings EDIT ENTRIES button is already configured.")
else:
    raise SystemExit("Could not find the DraftKings /entry/upload button block.")
