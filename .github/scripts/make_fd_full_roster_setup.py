from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# Move the FanDuel workflow out of the narrow Run column.
old = '''    with build_cols[2]:
        st.write("### Run")
        fd_sim_button = st.button(
            "SIM",
            type="primary",
            use_container_width=True,
            key="fd_sim_" + lineup_mode.replace(" ", "_").lower(),
            help="Runs player simulations, builds your lineups, builds the opponent field, and runs the contest comparison."
        )
        fd_run_all_clicked = fd_sim_button
        fd_sim_clicked = fd_sim_button
        fd_build_clicked = fd_sim_button
        fd_contest_clicked = fd_sim_button
        fd_workflow_status = None
        if fd_run_all_clicked:
'''
new = '''    with build_cols[2]:
        st.write("### Run")
        fd_sim_button = st.button(
            "SIM",
            type="primary",
            use_container_width=True,
            key="fd_sim_" + lineup_mode.replace(" ", "_").lower(),
            help="Runs player simulations, builds your lineups, builds the opponent field, and runs the contest comparison."
        )
    fd_run_all_clicked = fd_sim_button
    fd_sim_clicked = fd_sim_button
    fd_build_clicked = fd_sim_button
    fd_contest_clicked = fd_sim_button
    fd_workflow_status = None
    if fd_run_all_clicked:
'''
if old in text:
    text = text.replace(old, new, 1)
    start = text.index('    if fd_run_all_clicked:\n', text.index(new))
    end_marker = '\n        st.stop()\n\nelse:\n'
    end = text.find(end_marker, start)
    if end == -1:
        raise SystemExit("FanDuel branch end not found")
    block = text[start:end]
    lines = block.splitlines(True)
    fixed = [lines[0]] + [(line[4:] if line.startswith('        ') else line) for line in lines[1:]]
    text = text[:start] + ''.join(fixed) + text[end:]

text = text.replace('st.write("### FanDuel Contest Sim + ROI")', 'st.write("### FanDuel Contest Summary")', 1)

# Replace the static rank-to-prize shortcut with simulation-by-simulation ROI.
start_token = '_fd_full_field = int(_fd_field_label or 65000)'
end_token = 'st.caption("Uses the supplied Hail Mary payout ladder through 65,000th place. Representative-field ranks are scaled to the full contest field.")'
start = text.find(start_token)
end = text.find(end_token, start)
if start == -1 or end == -1:
    raise SystemExit("FanDuel payout calculation block not found")
end += len(end_token)
indent = text[text.rfind('\n', 0, start) + 1:start]
replacement_lines = '''_fd_full_field = int(_fd_field_label or 65000)
_fd_rep_field = max(len(opponent_df), 1)
_fd_entry_count = min(_fd_my_entries, len(compared))
_fd_entry_pool = compared.nlargest(_fd_entry_count, "ContestScore").copy() if _fd_entry_count > 0 else compared.iloc[0:0].copy()

def _fd_prize_for_rank(rank):
    for lo, hi, prize in _fd_payout_tiers:
        if lo <= int(rank) <= hi:
            return float(prize)
    return 0.0

def _fd_tie_prize(first_rank, tie_count):
    first_rank = max(1, int(first_rank))
    tie_count = max(1, int(tie_count))
    last_rank = min(_fd_full_field, first_rank + tie_count - 1)
    if first_rank > _fd_full_field:
        return 0.0
    return float(np.mean([_fd_prize_for_rank(r) for r in range(first_rank, last_rank + 1)]))

_fd_sim_count = min(300, len(simulated_scores))
_fd_expected_winnings = 0.0
if _fd_entry_count > 0 and _fd_sim_count > 0:
    _fd_sim_indices = np.linspace(0, len(simulated_scores) - 1, _fd_sim_count, dtype=int)
    _fd_player_vectors = {
        str(col): pd.to_numeric(simulated_scores[col], errors="coerce").fillna(0.0).to_numpy(dtype=float)[_fd_sim_indices]
        for col in simulated_scores.columns
    }
    def _fd_lineup_vector(row):
        total = np.zeros(_fd_sim_count, dtype=float)
        for slot in fd_slots:
            player = str(row.get(slot, ""))
            values = _fd_player_vectors.get(player)
            if values is not None:
                total += values
        return total
    _fd_opp_matrix = np.vstack([_fd_lineup_vector(row) for _, row in opponent_df.iterrows()])
    _fd_user_matrix = np.vstack([_fd_lineup_vector(row) for _, row in _fd_entry_pool.iterrows()])
    _fd_scale = max(_fd_full_field - _fd_entry_count, 1) / max(_fd_rep_field, 1)
    _fd_prize_totals = np.zeros(_fd_entry_count, dtype=float)
    for sim_i in range(_fd_sim_count):
        field_scores = _fd_opp_matrix[:, sim_i]
        for entry_i in range(_fd_entry_count):
            score = _fd_user_matrix[entry_i, sim_i]
            greater = int(np.sum(field_scores > score))
            tied = int(np.sum(np.isclose(field_scores, score, rtol=0.0, atol=1e-9)))
            full_greater = int(round(greater * _fd_scale))
            full_tied = max(1, int(round(max(tied, 1) * _fd_scale)))
            first_rank = 1 + full_greater
            _fd_prize_totals[entry_i] += _fd_tie_prize(first_rank, full_tied)
    _fd_entry_pool["Expected Prize ($)"] = _fd_prize_totals / _fd_sim_count
    _fd_entry_pool["Expected Net ($)"] = _fd_entry_pool["Expected Prize ($)"] - float(_fd_fee)
    _fd_entry_pool["Expected ROI (%)"] = 100.0 * _fd_entry_pool["Expected Net ($)"] / max(float(_fd_fee), 0.01)
    _fd_expected_winnings = float(_fd_entry_pool["Expected Prize ($)"].sum())
_fd_expected_profit = _fd_expected_winnings - _fd_total_fees
_fd_expected_roi = 100.0 * _fd_expected_profit / max(_fd_total_fees, 0.01)
_fd_roi_cols[2].metric("Expected Winnings", f"${_fd_expected_winnings:,.2f}")
_fd_roi_cols[3].metric("Expected Profit", f"${_fd_expected_profit:,.2f}")
_fd_roi_cols[4].metric("Expected ROI", f"{_fd_expected_roi:,.1f}%")
st.caption(f"ROI uses {_fd_sim_count:,} simulation-by-simulation contest outcomes, the supplied payout ladder, full-field scaling, and tie splitting.")'''.splitlines()
replacement = '\n'.join(indent + line if line else '' for line in replacement_lines)
text = text[:start] + replacement + text[end:]

path.write_text(text, encoding="utf-8")
