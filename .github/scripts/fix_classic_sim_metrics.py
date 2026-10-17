from pathlib import Path

p = Path('dfs_app.py')
s = p.read_text()
old = '''                        _denom = max(1, len(_roi_values))
                        user_lineups["Expected Prize ($)"] = _prize_sums / _denom
                        user_lineups["Estimated Full Field Rank"] = np.rint(_rank_sums / _denom).astype(int)
'''
new = '''                        _denom = max(1, len(_roi_values))
                        user_lineups["Expected Prize ($)"] = _prize_sums / _denom
                        user_lineups["Estimated Full Field Rank"] = np.rint(_rank_sums / _denom).astype(int)

                        # Finish-rate metrics must come from the same simulated contest
                        # ranks used for ROI. The older projected-points helper can make
                        # every selected lineup appear 100% Top1/Top5/Top10/Cash.
                        _top1_hits = np.zeros(len(user_lineups), dtype=float)
                        _top5_hits = np.zeros(len(user_lineups), dtype=float)
                        _top10_hits = np.zeros(len(user_lineups), dtype=float)
                        _cash_hits = np.zeros(len(user_lineups), dtype=float)
                        _cash_rank = max(int(classic_contest["payouts"][-1][1]), 1)
                        _top1_rank = max(1, int(np.ceil(full_field_size * 0.01)))
                        _top5_rank = max(1, int(np.ceil(full_field_size * 0.05)))
                        _top10_rank = max(1, int(np.ceil(full_field_size * 0.10)))
                        for _s in range(len(_roi_values)):
                            _sorted = np.sort(_opp_outcomes[_s])
                            _scores = _user_outcomes[_s]
                            _right = np.searchsorted(_sorted, _scores, side="right")
                            _better_sample = _sample_n - _right
                            _rank = 1 + np.rint((_better_sample / _sample_n) * _full_opponents).astype(int)
                            _top1_hits += (_rank <= _top1_rank)
                            _top5_hits += (_rank <= _top5_rank)
                            _top10_hits += (_rank <= _top10_rank)
                            _cash_hits += (_rank <= _cash_rank)
                        user_lineups["Top1"] = _top1_hits / _denom
                        user_lineups["Top5"] = _top5_hits / _denom
                        user_lineups["Top10"] = _top10_hits / _denom
                        user_lineups["CashRate"] = _cash_hits / _denom
                        user_lineups["AvgPercentile"] = 1.0 - ((user_lineups["Estimated Full Field Rank"] - 1) / max(1, full_field_size - 1))
'''
if old not in s:
    raise SystemExit('target block not found')
s = s.replace(old, new, 1)
p.write_text(s)
