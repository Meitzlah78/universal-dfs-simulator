from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()

anchor = '''    if payout_schedule is not None and len(payout_schedule) < estimated_full_field_size:\n        st.caption(\n            f"Payout estimates use sampled percentiles scaled to an estimated "\n            f"{estimated_full_field_size:,}-entry contest. The simulator scores "\n            f"{total_field:,} opponents per simulation, so winnings and ROI are estimates, "\n            f"not exact full-field results."\n        )\n\n'''
insert = anchor + '''    # Payout schedule metadata is invariant across scoring batches. Build it once\n    # so all worker threads reuse the same paid-position count and prefix sums.\n    paid_positions = (\n        min(int(np.count_nonzero(payout_schedule > 0)), estimated_full_field_size)\n        if payout_schedule is not None\n        else int(np.ceil(estimated_full_field_size * 0.10))\n    )\n    if payout_schedule is not None and len(payout_schedule) > 0:\n        rank_axis = np.arange(1, len(payout_schedule) + 1, dtype=np.int64)\n        rank_prizes = np.where(rank_axis <= estimated_full_field_size, payout_schedule, 0.0)\n        cumulative_prizes = np.concatenate(\n            ([0.0], np.cumsum(rank_prizes, dtype=np.float64))\n        )\n    else:\n        cumulative_prizes = None\n\n'''
if anchor not in text:
    raise SystemExit('payout setup anchor not found')
text = text.replace(anchor, insert, 1)

old = '''        paid_positions = (\n            min(int(np.count_nonzero(payout_schedule > 0)), estimated_full_field_size)\n            if payout_schedule is not None\n            else int(np.ceil(estimated_full_field_size * 0.10))\n        )\n        batch_cash = np.sum(estimated_ranks <= paid_positions, axis=0, dtype=np.float64)\n'''
new = '''        batch_cash = np.sum(estimated_ranks <= paid_positions, axis=0, dtype=np.float64)\n'''
if old not in text:
    raise SystemExit('per-batch paid positions block not found')
text = text.replace(old, new, 1)

old = '''            rank_axis = np.arange(1, len(payout_schedule) + 1, dtype=np.int64)\n            rank_prizes = np.where(rank_axis <= estimated_full_field_size, payout_schedule, 0.0)\n            cumulative_prizes = np.concatenate(([0.0], np.cumsum(rank_prizes, dtype=np.float64)))\n            safe_start = np.clip(tie_start_ranks - 1, 0, len(payout_schedule))\n'''
new = '''            safe_start = np.clip(tie_start_ranks - 1, 0, len(payout_schedule))\n'''
if old not in text:
    raise SystemExit('per-batch payout prefix block not found')
text = text.replace(old, new, 1)

path.write_text(text)
