from pathlib import Path

path = Path("dk_showdown_engine.py")
text = path.read_text(encoding="utf-8")
old = "    top_count = max(10, min(40, total))\n"
new = "    top_count = min(max(10, min(40, total)), total)\n"
if text.count(old) != 1:
    raise SystemExit(f"SAFE_ABORT: expected one top_count line, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
