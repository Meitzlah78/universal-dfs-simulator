from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old_import = "from dk_showdown_engine import candidate_score as dk_showdown_candidate_score\n"
new_import = "from dk_showdown_engine import (\n    candidate_score as dk_showdown_candidate_score,\n    duplicate_expansion_weights as dk_duplicate_expansion_weights,\n)\n"
if new_import not in text:
    if text.count(old_import) != 1:
        raise SystemExit(f"SAFE_ABORT: expected one DK engine import anchor, found {text.count(old_import)}")
    text = text.replace(old_import, new_import, 1)

start_anchor = "    centered_log_weights = log_weights - np.max(log_weights)\n"
end_anchor = "    rng = np.random.default_rng(seed)\n"
if text.count(start_anchor) != 1:
    raise SystemExit(f"SAFE_ABORT: expected one duplicate-weight block start, found {text.count(start_anchor)}")
start = text.index(start_anchor)
end = text.index(end_anchor, start)
legacy = text[start:end]
required = [
    "base_weights = np.exp(centered_log_weights * 0.38)",
    "broad_count = max(250, min(1800, max(250, total // 5)))",
    "top_count = max(10, min(40, total))",
    "weights = 0.76 * base_weights + 0.20 * broad_weights + 0.04 * top_weights",
]
if not all(token in legacy for token in required):
    raise SystemExit("SAFE_ABORT: duplicate-weight block did not match expected legacy structure")

replacement = "    weights = dk_duplicate_expansion_weights(log_weights)\n\n"
text = text[:start] + replacement + text[end:]
path.write_text(text)
