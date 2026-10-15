from pathlib import Path

p = Path('dfs_app.py')
s = p.read_text()
old = '''                            compared.loc[_fd_selected_idx, "Cash %"] = 100.0 * _fd_cash / _fd_scenario_count
'''
new = '''                            compared.loc[_fd_selected_idx, "Cash %"] = 100.0 * _fd_cash / _fd_scenario_count

                            # IMPORTANT: the canonical ranking/export columns must reflect
                            # scenario-level contest finish rates, not the earlier one-time
                            # projection percentile flags from add_field_ranking_metrics().
                            # Keep unselected candidates blank because they were not jointly
                            # evaluated for payout/ROI in the real contest entry set.
                            for _canonical in ["WinRate", "Top1", "Top5", "Top10", "CashRate", "AvgPercentile", "ContestScore"]:
                                compared[_canonical] = np.nan
                            _fd_win_rate = _fd_win / _fd_scenario_count
                            _fd_top1_rate = _fd_top1 / _fd_scenario_count
                            _fd_top5_rate = _fd_top5 / _fd_scenario_count
                            _fd_top10_rate = _fd_top10 / _fd_scenario_count
                            _fd_cash_rate = _fd_cash / _fd_scenario_count
                            compared.loc[_fd_selected_idx, "WinRate"] = _fd_win_rate
                            compared.loc[_fd_selected_idx, "Top1"] = _fd_top1_rate
                            compared.loc[_fd_selected_idx, "Top5"] = _fd_top5_rate
                            compared.loc[_fd_selected_idx, "Top10"] = _fd_top10_rate
                            compared.loc[_fd_selected_idx, "CashRate"] = _fd_cash_rate
                            compared.loc[_fd_selected_idx, "ContestScore"] = (
                                _fd_top1_rate * 0.40
                                + _fd_top5_rate * 0.25
                                + _fd_top10_rate * 0.20
                                + _fd_cash_rate * 0.10
                                + _fd_win_rate * 0.05
                            )

                            # Persist scenario-level scoring diagnostics so we can verify
                            # whether the ROI problem is field construction or contest scoring.
                            # This compares the exact jointly entered user lineups with the
                            # exact opponent field under the same PBP scenarios.
                            _fd_diag_scenarios = []
                            for _scenario in _fd_scenario_idx[:min(50, len(_fd_scenario_idx))]:
                                _row = _fd_values[_scenario]
                                _diag_field = np.zeros(len(opponent_df), dtype=float)
                                _diag_user = np.zeros(_fd_n_user, dtype=float)
                                for _slot_pos, _slot in enumerate(_fd_roi_slots):
                                    _mult = 1.5 if _slot == "MVP" else 1.0
                                    _diag_field += _row[_fd_field_matrix[:, _slot_pos]] * _mult
                                    _diag_user += _row[_fd_user_matrix[:, _slot_pos]] * _mult
                                _fd_diag_scenarios.append({
                                    "Opponent Avg Score": float(np.mean(_diag_field)),
                                    "My Entries Avg Score": float(np.mean(_diag_user)),
                                    "Opponent P90 Score": float(np.quantile(_diag_field, 0.90)),
                                    "Opponent P99 Score": float(np.quantile(_diag_field, 0.99)),
                                    "My Best Score": float(np.max(_diag_user)),
                                })
                            st.session_state["fd_full_roster_scoring_diagnostic"] = pd.DataFrame(_fd_diag_scenarios)
'''
if new in s:
    print('already patched')
    raise SystemExit(0)
if old not in s:
    raise SystemExit('target not found')
s = s.replace(old, new, 1)
p.write_text(s)
print('patched')
