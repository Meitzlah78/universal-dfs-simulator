from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''    # Calibrate the duplicate distribution to completed large-field DK Showdown data.\n    # Monday BUF@LAR had a normal long tail of unique lineups but also a small set of\n    # very chalky constructions duplicated hundreds of times. A single tempered curve\n    # produced the right average duplicates but made the top lineup far too unique.\n    # Use a flatter base for lineup diversity plus an 8% chalk component concentrated\n    # on the most popular constructions. This preserves the broad field while allowing\n    # realistic 100+ / 300+ duplicate clusters in large contests.\n    centered_log_weights = log_weights - np.max(log_weights)\n    base_weights = np.exp(centered_log_weights * 0.45)\n    base_weights /= base_weights.sum()\n\n    chalk_count = max(10, min(20, total))\n    chalk_indices = np.argpartition(log_weights, -chalk_count)[-chalk_count:]\n    chalk_weights = np.zeros(total, dtype=np.float64)\n    chalk_strength = np.exp(centered_log_weights[chalk_indices] * 1.30)\n    if chalk_strength.sum() > 0:\n        chalk_weights[chalk_indices] = chalk_strength / chalk_strength.sum()\n        weights = 0.92 * base_weights + 0.08 * chalk_weights\n    else:\n        weights = base_weights\n    weights /= weights.sum()\n'''

new = '''    # Calibrated from the actual 59,453-entry BUF@LAR DK Dime Package field:\n    # 12,029 unique lineups, median duplicate count 2, max 397, with a broad\n    # duplicate tail (1,340 lineups at 10+ copies and 569 at 20+). The prior\n    # 20-lineup chalk bucket over-concentrated duplication into too few lineups.\n    # Spread the chalk component across a much wider slice of the candidate field\n    # while retaining a small sharper component for the very chalkiest builds.\n    centered_log_weights = log_weights - np.max(log_weights)\n    base_weights = np.exp(centered_log_weights * 0.38)\n    base_weights /= base_weights.sum()\n\n    broad_count = max(250, min(1800, max(250, total // 5)))\n    broad_count = min(broad_count, total)\n    broad_indices = np.argpartition(log_weights, -broad_count)[-broad_count:]\n    broad_weights = np.zeros(total, dtype=np.float64)\n    broad_strength = np.exp(centered_log_weights[broad_indices] * 0.80)\n    if broad_strength.sum() > 0:\n        broad_weights[broad_indices] = broad_strength / broad_strength.sum()\n\n    top_count = max(10, min(40, total))\n    top_indices = np.argpartition(log_weights, -top_count)[-top_count:]\n    top_weights = np.zeros(total, dtype=np.float64)\n    top_strength = np.exp(centered_log_weights[top_indices] * 1.20)\n    if top_strength.sum() > 0:\n        top_weights[top_indices] = top_strength / top_strength.sum()\n\n    weights = 0.76 * base_weights + 0.20 * broad_weights + 0.04 * top_weights\n    weights /= weights.sum()\n'''

if new in text:
    print("Actual-field Showdown duplicate calibration already applied.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Calibrated Showdown duplicate distribution to actual Monday field.")
else:
    raise SystemExit("Could not find prior Showdown duplicate calibration block")
