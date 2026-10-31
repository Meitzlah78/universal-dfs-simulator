from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()

anchor = '''                        compared["FD Joint Entry"] = False
                        compared.loc[_fd_selected_idx, "FD Joint Entry"] = True

                        _fd_columns = {str(name): i for i, name in enumerate(_fd_roi_sim.columns.astype(str))}
'''
insert = '''                        compared["FD Joint Entry"] = False
                        compared.loc[_fd_selected_idx, "FD Joint Entry"] = True

                        # Full Roster final ROI gets a larger representative field without
                        # slowing candidate construction/ranking. The normal builder remains
                        # at 10K opponents; only the selected joint portfolio uses up to 50K.
                        _fd_final_field = opponent_df
                        if lineup_mode == "Full Roster" and len(opponent_df) < 50000:
                            _fd_extra_target = 50000 - len(opponent_df)
                            _fd_extra_rows = []
                            _fd_extra_attempts = 0
                            _fd_extra_rng = np.random.default_rng(50123)
                            _fd_extra_roster = [
                                ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                                ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                                ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}),
                                ("D", {"D", "DST", "DEF"}),
                            ]
                            _fd_final_progress = st.progress(0, text="Building larger final ROI field: 10,000 / 50,000")
                            while len(_fd_extra_rows) < _fd_extra_target and _fd_extra_attempts < max(600000, _fd_extra_target * 15):
                                _fd_extra_attempts += 1
                                _fd_chosen_final = {}
                                _fd_used_final = set()
                                _fd_salary_final = 0
                                _fd_points_final = 0.0
                                for _fd_pos_final, (_fd_slot_final, _fd_eligible_final) in enumerate(_fd_extra_roster):
                                    _fd_choices_final = fd_full_field_cache.get(_fd_slot_final, np.asarray([], dtype=int))
                                    if _fd_used_final:
                                        _fd_choices_final = _fd_choices_final[~np.isin(_fd_choices_final, np.fromiter(_fd_used_final, dtype=int))]
                                    if not len(_fd_choices_final):
                                        break
                                    _fd_remaining_final = _fd_extra_roster[_fd_pos_final + 1:]
                                    if _fd_remaining_final:
                                        if any(s not in fd_field_slot_bounds for s, _ in _fd_remaining_final):
                                            _fd_choices_final = np.asarray([], dtype=int)
                                        else:
                                            _fd_min_remaining_final = sum(fd_field_slot_bounds[s][0] for s, _ in _fd_remaining_final)
                                            _fd_max_remaining_final = sum(fd_field_slot_bounds[s][1] for s, _ in _fd_remaining_final)
                                            _fd_candidate_salary_final = _fd_salary_final + fd_field_salaries[_fd_choices_final]
                                            _fd_choices_final = _fd_choices_final[
                                                (_fd_candidate_salary_final + _fd_max_remaining_final >= _fd_opponent_salary_min)
                                                & (_fd_candidate_salary_final + _fd_min_remaining_final <= _fd_opponent_salary_max)
                                            ]
                                    else:
                                        _fd_candidate_salary_final = _fd_salary_final + fd_field_salaries[_fd_choices_final]
                                        _fd_choices_final = _fd_choices_final[
                                            (_fd_candidate_salary_final >= _fd_opponent_salary_min)
                                            & (_fd_candidate_salary_final <= _fd_opponent_salary_max)
                                        ]
                                    if not len(_fd_choices_final):
                                        break
                                    _fd_weights_final = np.clip(fd_weights[_fd_choices_final].astype(float), 0.0001, None)
                                    _fd_means_final = np.clip(fd_field_projections[_fd_choices_final].astype(float), 0.01, None)
                                    _fd_mean_scale_final = _fd_means_final / max(float(np.mean(_fd_means_final)), 0.01)
                                    _fd_weights_final *= np.power(_fd_mean_scale_final, 0.20)
                                    _fd_weights_final /= _fd_weights_final.sum()
                                    _fd_pick_final = int(_fd_extra_rng.choice(_fd_choices_final, p=_fd_weights_final))
                                    _fd_chosen_final[_fd_slot_final] = str(fd_field_names[_fd_pick_final])
                                    _fd_used_final.add(_fd_pick_final)
                                    _fd_salary_final += int(fd_field_salaries[_fd_pick_final])
                                    _fd_points_final += float(fd_field_projections[_fd_pick_final])
                                if len(_fd_chosen_final) != len(fd_slots):
                                    continue
                                if _fd_salary_final < _fd_opponent_salary_min or _fd_salary_final > _fd_opponent_salary_max:
                                    continue
                                _fd_salary_accept_final = {
                                    60000: 1.00, 59900: 0.90, 59800: 0.72, 59700: 0.58,
                                    59600: 0.46, 59500: 0.36, 59400: 0.24, 59300: 0.18,
                                    59200: 0.13, 59100: 0.09, 59000: 0.06,
                                }.get(int(_fd_salary_final), 0.01 if _fd_salary_final >= 58000 else 0.002)
                                if _fd_extra_rng.random() > _fd_salary_accept_final:
                                    continue
                                _fd_extra_rows.append({**_fd_chosen_final, "Salary": _fd_salary_final, "ProjectedPoints": round(_fd_points_final, 2)})
                                if len(_fd_extra_rows) % 500 == 0 or len(_fd_extra_rows) >= _fd_extra_target:
                                    _fd_done_final = len(opponent_df) + len(_fd_extra_rows)
                                    _fd_final_progress.progress(min(1.0, _fd_done_final / 50000), text=f"Building larger final ROI field: {_fd_done_final:,} / 50,000")
                            _fd_final_progress.empty()
                            if _fd_extra_rows:
                                _fd_final_field = pd.concat([opponent_df, pd.DataFrame(_fd_extra_rows)], ignore_index=True)
                            st.caption(f"Final joint ROI representative field: {len(_fd_final_field):,} opponents (builder/ranking field remains {len(opponent_df):,}).")

                        _fd_columns = {str(name): i for i, name in enumerate(_fd_roi_sim.columns.astype(str))}
'''
if anchor not in text:
    raise SystemExit('selection anchor not found')
text = text.replace(anchor, insert, 1)
old = '''                        _fd_user_matrix = _fd_matrix_indices(compared.iloc[_fd_selected_idx])
                        _fd_field_matrix = _fd_matrix_indices(opponent_df)
'''
new = '''                        _fd_user_matrix = _fd_matrix_indices(compared.iloc[_fd_selected_idx])
                        _fd_field_matrix = _fd_matrix_indices(_fd_final_field)
'''
if old not in text:
    raise SystemExit('field matrix anchor not found')
text = text.replace(old, new, 1)
text = text.replace('''                                _field_scores = np.zeros(len(opponent_df), dtype=float)\n                                _user_scores = np.zeros(_fd_n_user, dtype=float)\n''', '''                                _field_scores = np.zeros(len(_fd_final_field), dtype=float)\n                                _user_scores = np.zeros(_fd_n_user, dtype=float)\n''', 1)
text = text.replace('''                            _fd_rep_n = max(len(opponent_df), 1)\n''', '''                            _fd_rep_n = max(len(_fd_final_field), 1)\n''', 1)
path.write_text(text)
