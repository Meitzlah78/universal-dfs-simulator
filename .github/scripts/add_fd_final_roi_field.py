from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
anchor = '''                        _fd_user_matrix = _fd_matrix_indices(compared.iloc[_fd_selected_idx])
                        _fd_field_matrix = _fd_matrix_indices(opponent_df)
'''
replacement = '''                        _fd_user_matrix = _fd_matrix_indices(compared.iloc[_fd_selected_idx])

                        # Final-portfolio ROI gets a larger, independent opponent sample without
                        # making the normal 5,000-lineup builder rank against more than 10,000.
                        # Reuse the already prepared Full Roster player/slot arrays and generate
                        # only the additional lineups needed here. DraftKings and FD Single Game
                        # never enter this Hail Mary Full Roster block.
                        _fd_final_field = opponent_df
                        _fd_final_target = 50000
                        if lineup_mode == "Full Roster" and len(opponent_df) < _fd_final_target:
                            _fd_extra_rows = []
                            _fd_extra_rng = np.random.default_rng(9127)
                            _fd_extra_attempts = 0
                            _fd_extra_needed = _fd_final_target - len(opponent_df)
                            _fd_extra_roster = [
                                ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                                ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                                ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}),
                                ("D", {"D", "DST", "DEF"}),
                            ]
                            while len(_fd_extra_rows) < _fd_extra_needed and _fd_extra_attempts < max(600000, _fd_extra_needed * 15):
                                _fd_extra_attempts += 1
                                _fd_chosen = {}
                                _fd_used_idx = set()
                                _fd_salary = 0
                                _fd_points = 0.0
                                for _fd_pos, (_fd_slot, _fd_eligible) in enumerate(_fd_extra_roster):
                                    _fd_choices = fd_full_field_cache.get(_fd_slot, np.asarray([], dtype=int))
                                    if _fd_used_idx:
                                        _fd_choices = _fd_choices[~np.isin(_fd_choices, np.fromiter(_fd_used_idx, dtype=int))]
                                    if not len(_fd_choices):
                                        break
                                    _fd_remaining = _fd_extra_roster[_fd_pos + 1:]
                                    if _fd_remaining:
                                        _fd_min_remaining = sum(fd_field_slot_bounds[s][0] for s, _ in _fd_remaining)
                                        _fd_max_remaining = sum(fd_field_slot_bounds[s][1] for s, _ in _fd_remaining)
                                        _fd_candidate_salary = _fd_salary + fd_field_salaries[_fd_choices]
                                        _fd_feasible = (
                                            (_fd_candidate_salary + _fd_max_remaining >= 59000)
                                            & (_fd_candidate_salary + _fd_min_remaining <= 60000)
                                        )
                                        _fd_choices = _fd_choices[_fd_feasible]
                                    else:
                                        _fd_candidate_salary = _fd_salary + fd_field_salaries[_fd_choices]
                                        _fd_choices = _fd_choices[(_fd_candidate_salary >= 59000) & (_fd_candidate_salary <= 60000)]
                                    if not len(_fd_choices):
                                        break
                                    _fd_w = np.clip(fd_weights[_fd_choices].astype(float), 0.0001, None)
                                    _fd_means = np.clip(fd_field_projections[_fd_choices].astype(float), 0.01, None)
                                    _fd_w *= np.power(_fd_means / max(float(np.mean(_fd_means)), 0.01), 0.20)
                                    _fd_w /= _fd_w.sum()
                                    _fd_pick = int(_fd_extra_rng.choice(_fd_choices, p=_fd_w))
                                    _fd_chosen[_fd_slot] = str(fd_field_names[_fd_pick])
                                    _fd_used_idx.add(_fd_pick)
                                    _fd_salary += int(fd_field_salaries[_fd_pick])
                                    _fd_points += float(fd_field_projections[_fd_pick])
                                if len(_fd_chosen) != len(fd_slots) or _fd_salary < 59000 or _fd_salary > 60000:
                                    continue
                                _fd_accept = {
                                    60000: 1.00, 59900: 0.90, 59800: 0.72, 59700: 0.58,
                                    59600: 0.46, 59500: 0.36, 59400: 0.24, 59300: 0.18,
                                    59200: 0.13, 59100: 0.09, 59000: 0.06,
                                }.get(int(_fd_salary), 0.01 if _fd_salary >= 58000 else 0.002)
                                if _fd_extra_rng.random() > _fd_accept:
                                    continue
                                _fd_extra_rows.append({**_fd_chosen, "Salary": _fd_salary, "ProjectedPoints": round(_fd_points, 2)})
                            if _fd_extra_rows:
                                _fd_final_field = pd.concat([opponent_df, pd.DataFrame(_fd_extra_rows)], ignore_index=True)
                            st.caption(f"Final FanDuel ROI field: {len(_fd_final_field):,} simulated opponents (builder field remains {len(opponent_df):,}).")

                        _fd_field_matrix = _fd_matrix_indices(_fd_final_field)
'''
if replacement in text:
    print("FanDuel final ROI field expansion already applied.")
elif anchor not in text:
    raise SystemExit("FanDuel ROI field matrix anchor not found")
else:
    text = text.replace(anchor, replacement, 1)
    text = text.replace('''                            _fd_rep_n = max(len(opponent_df), 1)''', '''                            _fd_rep_n = max(len(_fd_final_field), 1)''', 1)
    text = text.replace('''                                _field_scores = np.zeros(len(opponent_df), dtype=float)''', '''                                _field_scores = np.zeros(len(_fd_final_field), dtype=float)''', 1)
    path.write_text(text, encoding="utf-8")
    print("Added 50,000-opponent FanDuel final ROI field; 10,000-opponent builder field unchanged.")
