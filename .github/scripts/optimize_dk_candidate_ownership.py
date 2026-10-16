from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

anchor = '        ownership_index = {name: i for i, name in enumerate(available_players)}\n'
insert = anchor + '''        # Build the name->ownership lookup once. Candidate scoring reuses it thousands\n        # of times, so rebuilding this dictionary inside every candidate loop wastes CPU.\n        showdown_ownership_by_name = {\n            name: float(showdown_ownership_proxy[index])\n            for name, index in ownership_index.items()\n        }\n'''
if text.count(anchor) != 1:
    raise SystemExit(f"SAFE_ABORT: expected one ownership_index anchor, found {text.count(anchor)}")
if "showdown_ownership_by_name = {" in text:
    raise SystemExit("SAFE_ABORT: ownership map optimization already present")
text = text.replace(anchor, insert, 1)

old = '                    {name: float(showdown_ownership_proxy[index]) for name, index in ownership_index.items()},\n'
new = '                    showdown_ownership_by_name,\n'
if text.count(old) != 1:
    raise SystemExit(f"SAFE_ABORT: expected one per-candidate ownership map, found {text.count(old)}")
text = text.replace(old, new, 1)

path.write_text(text)
