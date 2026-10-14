from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''    # Temper the popularity curve so one high-ownership player does not dominate\n    # the entire simulated field.\n    log_weights = (log_weights - np.max(log_weights)) * 0.65\n    weights = np.exp(log_weights)\n    weights /= weights.sum()\n\n    rng = np.random.default_rng(seed)\n    sampled_indices = rng.choice(total, size=full_field_size, replace=True, p=weights)\n'''

new = '''    # Calibrate the duplicate distribution to completed large-field DK Showdown data.\n    # Monday BUF@LAR had a normal long tail of unique lineups but also a small set of\n    # very chalky constructions duplicated hundreds of times. A single tempered curve\n    # produced the right average duplicates but made the top lineup far too unique.\n    # Use a flatter base for lineup diversity plus an 8% chalk component concentrated\n    # on the most popular constructions. This preserves the broad field while allowing\n    # realistic 100+ / 300+ duplicate clusters in large contests.\n    centered_log_weights = log_weights - np.max(log_weights)\n    base_weights = np.exp(centered_log_weights * 0.45)\n    base_weights /= base_weights.sum()\n\n    chalk_count = max(10, min(20, total))\n    chalk_indices = np.argpartition(log_weights, -chalk_count)[-chalk_count:]\n    chalk_weights = np.zeros(total, dtype=np.float64)\n    chalk_strength = np.exp(centered_log_weights[chalk_indices] * 1.30)\n    if chalk_strength.sum() > 0:\n        chalk_weights[chalk_indices] = chalk_strength / chalk_strength.sum()\n        weights = 0.92 * base_weights + 0.08 * chalk_weights\n    else:\n        weights = base_weights\n    weights /= weights.sum()\n\n    rng = np.random.default_rng(seed)\n    sampled_indices = rng.choice(total, size=full_field_size, replace=True, p=weights)\n'''

if new in text:
    print("Showdown duplicate-tail calibration already applied.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Calibrated Showdown duplicate tail from completed contest data.")
else:
    raise SystemExit("Could not find Showdown field expansion weighting block")
