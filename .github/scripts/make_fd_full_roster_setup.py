from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

start_marker = "                    # TRUE FANDUEL ROI: score user and opponent lineups through the\n"
end_marker = '                    st.session_state["fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()] = compared\n'

start = s.find(start_marker)
end = s.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("FanDuel ROI block markers not found")

new_block = '''                    # FANDUEL CONTEST ROI: use the same portfolio idea as DraftKings.
                    # Select the user's actual entry count first, then score those entries
                    # TOGETHER against the same opponent field in every PBP scenario.
                    # User entries therefore compete with each other, and duplicate/equal
                    # scores share the occupied prizes instead of each entry being treated
                    # as if it were the only user lineup in the contest.
                    _fd_roi_contest = st.session_state.get("selected_fd_contest") or {}
                    _fd_roi_name = str(_fd_roi_contest.get("name", ""))
                    _fd_roi_fee = _fd_roi_contest.get("entry_fee")
                    _fd_roi_sim = st.session_state.get("fd_simulation_df_" + lineup_mode.replace(" ", "_").lower())
                    if (
                        lineup_mode == "Full Roster"
                        and "45K Sun NFL Hail Mary" in _fd_roi_name
                        and _fd_roi_fee is not None
                        and isinstance(_fd_roi_sim, pd.DataFrame)
                        and not _fd_roi_sim.empty
                        and len(opponent_df) > 0
                        and len(compared) > 0
                    ):
                        _fd_payout_tiers_roi = [
                            (1, 1, 2000.0), (2, 2, 1000.0), (3, 3, 750.0),
                            (4, 4, 500.0), (5, 5, 300.0), (6, 6, 200.0),
                            (7, 7, 150.0), (8, 8, 125.0), (9, 10, 100.0),
                            (11, 12, 75.0), (13, 15, 50.0), (16, 20, 30.0),
                            (21, 25, 20.0), (26, 30, 15.0), (31, 40, 10.0),
                            (41, 50, 7.50), (51, 75, 5.0), (76, 100, 4.0),
                            (101, 150, 3.0), (151, 300, 2.0), (301, 600, 1.50),
                            (601, 1000, 1.25), (1001, 3000, 1.0),
                            (3001, 7500, 0.80), (7501, 15000, 0.70),
                            (15001, 30000, 0.60), (30001, 65000, 0.50),
                        ]
                        # field_size is the contest capacity returned by FanDuel. Never
                        # substitute the last paid place (65,000) for total field size.
                        _fd_full_field_roi = int(
                            _fd_roi_contest.get("field_size")
                            or _fd_roi_contest.get("current_entries")
                            or (len(opponent_df) + int(_fd_roi_contest.get("your_entries") or 1))
                        )
                        _fd_my_entries_roi = max(1, min(
                            int(_fd_roi_contest.get("your_entries") or 1), len(compared)
                        ))
                        _fd_full_field_roi = max(_fd_full_field_roi, _fd_my_entries_roi + 1)
                        _fd_payout = np.zeros(_fd_full_field_roi + 1, dtype=float)
                        for _lo, _hi, _prize in _fd_payout_tiers_roi:
                            _fd_payout[max(1, _lo):min(_fd_full_field_roi, _hi) + 1] = float(_prize)
                        _fd_prefix = np.concatenate(([0.0], np.cumsum(_fd_payout[1:])))

                        # Choose the final entry set without using ROI itself. This avoids
                        # selecting on the same payout results we are trying to measure.
                        _fd_select_metric = "ContestScore" if "ContestScore" in compared.columns else "ProjectedPoints"
                        _fd_selected_idx = (
                            compared[_fd_select_metric].astype(float)
                            .nlargest(_fd_my_entries_roi).index.to_numpy(dtype=int)
                        )
                        compared["FD Joint Entry"] = False
                        compared.loc[_fd_selected_idx, "FD Joint Entry"] = True

                        _fd_columns = {str(name): i for i, name in enumerate(_fd_roi_sim.columns.astype(str))}
                        _fd_roi_slots = [slot for slot in fd_slots if slot in compared.columns and slot in opponent_df.columns]
                        def _fd_matrix_indices(frame):
                            return np.column_stack([
                                frame[slot].astype(str).map(_fd_columns).fillna(-1).to_numpy(dtype=int)
                                for slot in _fd_roi_slots
                            ])

                        _fd_user_matrix = _fd_matrix_indices(compared.iloc[_fd_selected_idx])
                        _fd_field_matrix = _fd_matrix_indices(opponent_df)
                        _fd_valid = (
                            bool(_fd_roi_slots)
                            and np.all(_fd_user_matrix >= 0)
                            and np.all(_fd_field_matrix >= 0)
                        )
                        if _fd_valid:
                            _fd_scenario_count = min(250, len(_fd_roi_sim))
                            _fd_scenario_idx = np.linspace(0, len(_fd_roi_sim) - 1, _fd_scenario_count, dtype=int)
                            _fd_n_user = len(_fd_selected_idx)
                            _fd_expected_prize = np.zeros(_fd_n_user, dtype=float)
                            _fd_win = np.zeros(_fd_n_user, dtype=float)
                            _fd_top1 = np.zeros(_fd_n_user, dtype=float)
                            _fd_top5 = np.zeros(_fd_n_user, dtype=float)
                            _fd_top10 = np.zeros(_fd_n_user, dtype=float)
                            _fd_cash = np.zeros(_fd_n_user, dtype=float)
                            _fd_cash_cut = max(1, max(hi for lo, hi, prize in _fd_payout_tiers_roi if prize > 0))
                            _fd_values = _fd_roi_sim.to_numpy(dtype=float)
                            _fd_rep_n = max(len(opponent_df), 1)
                            _fd_full_opponents = max(_fd_full_field_roi - _fd_n_user, 1)
                            _fd_scale = _fd_full_opponents / _fd_rep_n

                            for _scenario in _fd_scenario_idx:
                                _row = _fd_values[_scenario]
                                _field_scores = np.zeros(len(opponent_df), dtype=float)
                                _user_scores = np.zeros(_fd_n_user, dtype=float)
                                for _slot_pos, _slot in enumerate(_fd_roi_slots):
                                    _mult = 1.5 if _slot == "MVP" else 1.0
                                    _field_scores += _row[_fd_field_matrix[:, _slot_pos]] * _mult
                                    _user_scores += _row[_fd_user_matrix[:, _slot_pos]] * _mult

                                _sorted = np.sort(_field_scores)
                                _left = np.searchsorted(_sorted, _user_scores, side="left")
                                _right = np.searchsorted(_sorted, _user_scores, side="right")
                                _greater_field = np.rint((len(_sorted) - _right) * _fd_scale).astype(int)
                                _equal_field = np.rint((_right - _left) * _fd_scale).astype(int)

                                # Every one of the user's entries is in this same contest.
                                _greater_own = np.sum(
                                    _user_scores[None, :] > _user_scores[:, None], axis=1
                                )
                                _equal_own = np.sum(
                                    _user_scores[None, :] == _user_scores[:, None], axis=1
                                ) - 1
                                _greater = _greater_field + _greater_own
                                _equal = _equal_field + _equal_own
                                _rank_start = np.clip(_greater + 1, 1, _fd_full_field_roi)
                                _tie_count = np.maximum(_equal + 1, 1)
                                _rank_end = np.minimum(_rank_start + _tie_count - 1, _fd_full_field_roi)
                                _prize_sum = _fd_prefix[_rank_end] - _fd_prefix[_rank_start - 1]
                                _fd_expected_prize += _prize_sum / _tie_count
                                _fd_win += (_rank_start == 1) / _tie_count
                                _fd_top1 += (_rank_start <= max(1, int(np.ceil(_fd_full_field_roi * 0.01))))
                                _fd_top5 += (_rank_start <= max(1, int(np.ceil(_fd_full_field_roi * 0.05))))
                                _fd_top10 += (_rank_start <= max(1, int(np.ceil(_fd_full_field_roi * 0.10))))
                                _fd_cash += (_rank_start <= _fd_cash_cut)

                            _fd_expected_prize /= _fd_scenario_count
                            # ROI is only truthful for the selected joint entries. Do not
                            # show fake independent ROI on the other 4,980 candidates.
                            for _col in ["Expected Prize ($)", "Expected Net ($)", "Expected ROI (%)", "Win %", "Top 1%", "Top 5%", "Top 10%", "Cash %"]:
                                compared[_col] = np.nan
                            _fd_net = _fd_expected_prize - float(_fd_roi_fee)
                            compared.loc[_fd_selected_idx, "Expected Prize ($)"] = _fd_expected_prize
                            compared.loc[_fd_selected_idx, "Expected Net ($)"] = _fd_net
                            compared.loc[_fd_selected_idx, "Expected ROI (%)"] = 100.0 * _fd_net / max(float(_fd_roi_fee), 0.01)
                            compared.loc[_fd_selected_idx, "Win %"] = 100.0 * _fd_win / _fd_scenario_count
                            compared.loc[_fd_selected_idx, "Top 1%"] = 100.0 * _fd_top1 / _fd_scenario_count
                            compared.loc[_fd_selected_idx, "Top 5%"] = 100.0 * _fd_top5 / _fd_scenario_count
                            compared.loc[_fd_selected_idx, "Top 10%"] = 100.0 * _fd_top10 / _fd_scenario_count
                            compared.loc[_fd_selected_idx, "Cash %"] = 100.0 * _fd_cash / _fd_scenario_count

'''

s = s[:start] + new_block + s[end:]

# The summary must use the exact jointly-scored entries, not re-pick 20 lineups
# independently by their individual ROI after the contest simulation.
old_summary = '''                                _fd_entry_count = min(_fd_my_entries, len(compared))
                                _fd_rank_for_entries = "Expected ROI (%)" if "Expected ROI (%)" in compared.columns else "ContestScore"
                                _fd_entry_pool = compared.nlargest(_fd_entry_count, _fd_rank_for_entries) if _fd_entry_count > 0 else compared.iloc[0:0]
'''
new_summary = '''                                _fd_entry_count = min(_fd_my_entries, len(compared))
                                if "FD Joint Entry" in compared.columns and compared["FD Joint Entry"].fillna(False).any():
                                    _fd_entry_pool = compared[compared["FD Joint Entry"].fillna(False)].copy()
                                else:
                                    _fd_entry_pool = compared.nlargest(_fd_entry_count, "ContestScore") if _fd_entry_count > 0 else compared.iloc[0:0]
'''
if old_summary not in s:
    raise SystemExit("FanDuel contest summary entry-pool block not found")
s = s.replace(old_summary, new_summary, 1)

p.write_text(s)
print("Applied FanDuel joint-entry contest ROI: own entries compete together and ties split prizes")
