from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

start_marker = '''                        # Expected prize must average across the lineup's outcome distribution,
'''
end_marker = '''                        user_lineups["Entry Fee ($)"] = float(classic_contest["entry"])
'''
start = text.find(start_marker)
end = text.find(end_marker, start)
if start == -1 or end == -1:
    raise SystemExit('Classic ROI block not found; app left unchanged.')
end += len(end_marker)

replacement = '''                        # Calculate ROI from actual simulation outcomes instead of coarse
                        # Top-1/5/10 probability bands. Score the representative opponent
                        # field and every candidate lineup on the same simulation draws.
                        _sim_cols = [str(c) for c in sim_df.columns]
                        _sim_index = {name: i for i, name in enumerate(_sim_cols)}
                        _sim_values = sim_df.to_numpy(dtype=float, copy=False)
                        _roi_sims = min(len(_sim_values), 500)
                        if _roi_sims < len(_sim_values):
                            _roi_pick = np.linspace(0, len(_sim_values) - 1, _roi_sims, dtype=int)
                            _roi_values = _sim_values[_roi_pick]
                        else:
                            _roi_values = _sim_values

                        def _lineup_matrix(_df, _slots):
                            _mat = np.zeros((len(_sim_cols), len(_df)), dtype=np.float32)
                            for _j, (_, _row) in enumerate(_df.iterrows()):
                                for _slot in _slots:
                                    _name = str(_row.get(_slot, ''))
                                    _i = _sim_index.get(_name)
                                    if _i is not None:
                                        _mat[_i, _j] += 1.0
                            return _mat

                        _opp_slots = [slot for slot, _ in contest_slots]
                        _user_slots = [c for c in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"] if c in user_lineups.columns]
                        _opp_matrix = _lineup_matrix(contest_field_df, _opp_slots)
                        _user_matrix = _lineup_matrix(user_lineups, _user_slots)
                        _opp_outcomes = np.asarray(_roi_values @ _opp_matrix, dtype=np.float32)
                        _user_outcomes = np.asarray(_roi_values @ _user_matrix, dtype=np.float32)

                        def _classic_tie_prize(_start_rank, _end_rank):
                            _start_rank = max(1, int(_start_rank))
                            _end_rank = min(full_field_size, max(_start_rank, int(_end_rank)))
                            _total = 0.0
                            for _first, _last, _prize in classic_contest["payouts"]:
                                _a = max(_start_rank, int(_first))
                                _b = min(_end_rank, int(_last))
                                if _a <= _b:
                                    _total += (_b - _a + 1) * float(_prize)
                            return _total / float(_end_rank - _start_rank + 1)

                        _prize_sums = np.zeros(len(user_lineups), dtype=float)
                        _rank_sums = np.zeros(len(user_lineups), dtype=float)
                        _sample_n = max(1, len(contest_field_df))
                        _full_opponents = max(1, full_field_size - 1)
                        for _s in range(len(_roi_values)):
                            _sorted = np.sort(_opp_outcomes[_s])
                            _scores = _user_outcomes[_s]
                            _less = np.searchsorted(_sorted, _scores, side="left")
                            _right = np.searchsorted(_sorted, _scores, side="right")
                            _better_sample = _sample_n - _right
                            _equal_sample = _right - _less
                            _better_full = np.rint((_better_sample / _sample_n) * _full_opponents).astype(int)
                            _equal_full = np.rint((_equal_sample / _sample_n) * _full_opponents).astype(int)
                            for _j in range(len(user_lineups)):
                                _rank_start = 1 + int(_better_full[_j])
                                _rank_end = min(full_field_size, _rank_start + int(_equal_full[_j]))
                                _prize_sums[_j] += _classic_tie_prize(_rank_start, _rank_end)
                                _rank_sums[_j] += (_rank_start + _rank_end) / 2.0

                        _denom = max(1, len(_roi_values))
                        user_lineups["Expected Prize ($)"] = _prize_sums / _denom
                        user_lineups["Estimated Full Field Rank"] = np.rint(_rank_sums / _denom).astype(int)
                        user_lineups["Entry Fee ($)"] = float(classic_contest["entry"])
'''

text = text[:start] + replacement + text[end:]
path.write_text(text, encoding='utf-8')
print('Classic ROI now uses simulation-by-simulation ranks, exact payouts, and tie splitting.')
