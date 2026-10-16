from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
old = '''    _own_col = next((_own_lookup[k] for k in (\n        "projected own %", "ownership %", "projected ownership",\n        "projected own", "ownership", "own%", "own"\n    ) if k in _own_lookup), None)\n'''
new = '''    _own_col = next((_own_lookup[k] for k in (\n        "field flex own %", "field own %", "projected own %", "ownership %",\n        "projected ownership", "projected own", "ownership", "own%", "own"\n    ) if k in _own_lookup), None)\n'''
if new in text:
    print("DK Showdown field ownership aliases already installed.")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Installed DK Showdown Field FLEX/Field Own ownership priority.")
else:
    raise SystemExit("Could not find DK Showdown ownership alias block")
