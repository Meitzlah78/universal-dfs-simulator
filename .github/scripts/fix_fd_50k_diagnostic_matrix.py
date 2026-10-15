from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()

old = '''                        _fd_user_matrix = _fd_matrix_indices(compared.iloc[_fd_selected_idx])
                        _fd_field_matrix = _fd_matrix_indices(_fd_final_field)
                        _fd_valid = (
'''
new = '''                        _fd_user_matrix = _fd_matrix_indices(compared.iloc[_fd_selected_idx])
                        _fd_field_matrix = _fd_matrix_indices(_fd_final_field)
                        # Candidate diagnostics intentionally stay on the original 10K builder field.
                        # Keep a separate matrix because _fd_field_matrix now represents the 50K
                        # final-ROI field and cannot be indexed into a 10K score vector.
                        _fd_diag_field_matrix = _fd_matrix_indices(opponent_df)
                        _fd_valid = (
'''
if old not in text:
    raise SystemExit('matrix anchor not found')
text = text.replace(old, new, 1)

old2 = '''                                    _field_scores = np.zeros(len(opponent_df), dtype=float)
                                    _candidate_scores = np.zeros(_fd_all_n, dtype=float)
                                    for _slot_pos, _slot in enumerate(_fd_roi_slots):
                                        _mult = 1.5 if _slot == "MVP" else 1.0
                                        _field_scores += _row[_fd_field_matrix[:, _slot_pos]] * _mult
                                        _candidate_scores += _row[_fd_all_user_matrix[:, _slot_pos]] * _mult
                                    _sorted_field = np.sort(_field_scores)
                                    _right = np.searchsorted(_sorted_field, _candidate_scores, side="right")
                                    _greater = np.rint((len(_sorted_field) - _right) * _fd_scale).astype(int)
'''
new2 = '''                                    _field_scores = np.zeros(len(opponent_df), dtype=float)
                                    _candidate_scores = np.zeros(_fd_all_n, dtype=float)
                                    for _slot_pos, _slot in enumerate(_fd_roi_slots):
                                        _mult = 1.5 if _slot == "MVP" else 1.0
                                        _field_scores += _row[_fd_diag_field_matrix[:, _slot_pos]] * _mult
                                        _candidate_scores += _row[_fd_all_user_matrix[:, _slot_pos]] * _mult
                                    _sorted_field = np.sort(_field_scores)
                                    _right = np.searchsorted(_sorted_field, _candidate_scores, side="right")
                                    _fd_diag_scale = _fd_full_opponents / max(len(opponent_df), 1)
                                    _greater = np.rint((len(_sorted_field) - _right) * _fd_diag_scale).astype(int)
'''
if old2 not in text:
    raise SystemExit('diagnostic scoring anchor not found')
text = text.replace(old2, new2, 1)
path.write_text(text)
print('Fixed 10K diagnostic matrix vs 50K final ROI matrix mismatch')
