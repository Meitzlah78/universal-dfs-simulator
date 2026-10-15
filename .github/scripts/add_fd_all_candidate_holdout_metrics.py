from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

if '"Diagnostic Top 1%"' in text:
    print("All-candidate holdout diagnostics already present.")
    raise SystemExit(0)

marker = '''                            # Persist scenario-level scoring diagnostics so we can verify
'''
pos = text.find(marker)
if pos < 0:
    raise SystemExit("Could not find FanDuel holdout diagnostic insertion point")

block = '''                            # Evaluate every generated candidate independently against the SAME
                            # holdout opponent field. These are diagnostic finish rates only; they
                            # are intentionally separate from joint-entry payout/ROI metrics.
                            _fd_all_user_matrix = _fd_matrix_indices(compared)
                            if np.all(_fd_all_user_matrix >= 0):
                                _fd_all_n = len(compared)
                                _fd_diag_win = np.zeros(_fd_all_n, dtype=float)
                                _fd_diag_top1 = np.zeros(_fd_all_n, dtype=float)
                                _fd_diag_top5 = np.zeros(_fd_all_n, dtype=float)
                                _fd_diag_top10 = np.zeros(_fd_all_n, dtype=float)
                                _fd_diag_cash = np.zeros(_fd_all_n, dtype=float)
                                for _scenario in _fd_scenario_idx:
                                    _row = _fd_values[_scenario]
                                    _field_scores = np.zeros(len(opponent_df), dtype=float)
                                    _candidate_scores = np.zeros(_fd_all_n, dtype=float)
                                    for _slot_pos, _slot in enumerate(_fd_roi_slots):
                                        _mult = 1.5 if _slot == "MVP" else 1.0
                                        _field_scores += _row[_fd_field_matrix[:, _slot_pos]] * _mult
                                        _candidate_scores += _row[_fd_all_user_matrix[:, _slot_pos]] * _mult
                                    _sorted_field = np.sort(_field_scores)
                                    _right = np.searchsorted(_sorted_field, _candidate_scores, side="right")
                                    _greater = np.rint((len(_sorted_field) - _right) * _fd_scale).astype(int)
                                    _rank = np.clip(_greater + 1, 1, _fd_full_field_roi)
                                    _fd_diag_win += (_rank == 1)
                                    _fd_diag_top1 += (_rank <= max(1, int(np.ceil(_fd_full_field_roi * 0.01))))
                                    _fd_diag_top5 += (_rank <= max(1, int(np.ceil(_fd_full_field_roi * 0.05))))
                                    _fd_diag_top10 += (_rank <= max(1, int(np.ceil(_fd_full_field_roi * 0.10))))
                                    _fd_diag_cash += (_rank <= _fd_cash_cut)
                                compared["Diagnostic Win %"] = 100.0 * _fd_diag_win / _fd_scenario_count
                                compared["Diagnostic Top 1%"] = 100.0 * _fd_diag_top1 / _fd_scenario_count
                                compared["Diagnostic Top 5%"] = 100.0 * _fd_diag_top5 / _fd_scenario_count
                                compared["Diagnostic Top 10%"] = 100.0 * _fd_diag_top10 / _fd_scenario_count
                                compared["Diagnostic Cash %"] = 100.0 * _fd_diag_cash / _fd_scenario_count

'''
text = text[:pos] + block + text[pos:]
path.write_text(text)
print("Added holdout finish-rate diagnostics for all FanDuel candidates.")
