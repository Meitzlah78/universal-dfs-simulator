from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# Make the right-side FanDuel Run/results area much wider and easier to read.
old = '    build_cols = st.columns([1, 1, 0.65])'
new = '    build_cols = st.columns([0.75, 0.75, 2.5])'
if old not in text:
    raise SystemExit("FanDuel build column layout not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
