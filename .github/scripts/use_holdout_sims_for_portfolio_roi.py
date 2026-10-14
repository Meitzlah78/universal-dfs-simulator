from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# Split simulations once: first half ranks/selects candidates, second half is an
# untouched holdout used only after the final portfolio has been chosen.
old = '''    n_candidates = len(candidate_idx)\n    n_sims = len(simulation_df)\n    total_field = len(contest_idx)\n'''
new = '''    n_candidates = len(candidate_idx)\n    n_sims = len(simulation_df)\n    selection_n_sims = max(1, n_sims // 2)\n    holdout_start = selection_n_sims\n    holdout_n_sims = max(1, n_sims - holdout_start)\n    total_field = len(contest_idx)\n'''
if new not in text:
    if old not in text:
        raise SystemExit("Could not find simulation-count block")
    text = text.replace(old, new, 1)

old = '''    batch_ranges = [\n        (batch_start, min(batch_start + batch_size, n_sims))\n        for batch_start in range(0, n_sims, batch_size)\n    ]\n'''
new = '''    batch_ranges = [\n        (batch_start, min(batch_start + batch_size, selection_n_sims))\n        for batch_start in range(0, selection_n_sims, batch_size)\n    ]\n'''
if new not in text:
    if old not in text:
        raise SystemExit("Could not find candidate batch ranges")
    text = text.replace(old, new, 1)

# Candidate metrics are based only on the selection half.
for col in ["WinRate", "Top1", "Top5", "Top10", "CashRate", "AvgPercentile"]:
    old = f'results_df["{col}"] = '
# Replace the exact normalization block once.
old = '''    results_df["WinRate"] = win_rates / n_sims\n    results_df["Top1"] = top1_rates / n_sims\n    results_df["Top5"] = top5_rates / n_sims\n    results_df["Top10"] = top10_rates / n_sims\n    results_df["CashRate"] = cash_rates / n_sims\n    results_df["AvgPercentile"] = avg_percentiles / n_sims\n\n    if payout_schedule is not None:\n        results_df["Expected Prize ($)"] = expected_prize_totals / n_sims\n'''
new = '''    results_df["WinRate"] = win_rates / selection_n_sims\n    results_df["Top1"] = top1_rates / selection_n_sims\n    results_df["Top5"] = top5_rates / selection_n_sims\n    results_df["Top10"] = top10_rates / selection_n_sims\n    results_df["CashRate"] = cash_rates / selection_n_sims\n    results_df["AvgPercentile"] = avg_percentiles / selection_n_sims\n\n    if payout_schedule is not None:\n        results_df["Expected Prize ($)"] = expected_prize_totals / selection_n_sims\n'''
if new not in text:
    if old not in text:
        raise SystemExit("Could not find candidate normalization block")
    text = text.replace(old, new, 1)

# Joint portfolio evaluation must use only unseen holdout simulations.
old = '''            for _portfolio_batch_start in range(0, n_sims, _portfolio_batch_size):\n                _portfolio_batch_end = min(_portfolio_batch_start + _portfolio_batch_size, n_sims)\n'''
new = '''            for _portfolio_batch_start in range(holdout_start, n_sims, _portfolio_batch_size):\n                _portfolio_batch_end = min(_portfolio_batch_start + _portfolio_batch_size, n_sims)\n'''
if new not in text:
    if old not in text:
        raise SystemExit("Could not find portfolio evaluation loop")
    text = text.replace(old, new, 1)

old = '''            portfolio_df["Expected Prize ($)"] = _portfolio_prize_totals / n_sims\n'''
new = '''            portfolio_df["Expected Prize ($)"] = _portfolio_prize_totals / holdout_n_sims\n'''
if new not in text:
    if old not in text:
        raise SystemExit("Could not find portfolio prize normalization")
    text = text.replace(old, new, 1)

old = '''            _portfolio_total_prizes = float(_portfolio_prize_totals.sum() / n_sims)\n'''
new = '''            _portfolio_total_prizes = float(_portfolio_prize_totals.sum() / holdout_n_sims)\n'''
if new not in text:
    if old not in text:
        raise SystemExit("Could not find portfolio total-prize normalization")
    text = text.replace(old, new, 1)

old = '''                "Joint portfolio estimate: the selected entries are scored together against the sampled field, "\n                "including ties between your own entries. Full-field ranks and winnings remain estimates."\n'''
new = '''                "Holdout portfolio estimate: lineups are selected using one half of the simulations, then "\n                "ROI is measured on the untouched second half. Entries are scored together and ties are split. "\n                "Full-field ranks and winnings remain estimates."\n'''
if new not in text:
    if old not in text:
        raise SystemExit("Could not find portfolio caption")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Portfolio ROI now uses unseen holdout simulations.")
