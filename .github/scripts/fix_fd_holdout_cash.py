from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()

old = '''                            _fd_scenario_count = min(250, len(_fd_roi_sim))
                            _fd_scenario_idx = np.linspace(0, len(_fd_roi_sim) - 1, _fd_scenario_count, dtype=int)
'''
new = '''                            # Evaluate final contest results on a deterministic holdout slice of
                            # PBP outcomes rather than the early scenarios used while generating/
                            # ranking candidates. This reduces selection leakage in final ROI rates.
                            _fd_all_scenarios = np.arange(len(_fd_roi_sim), dtype=int)
                            _fd_holdout_start = len(_fd_all_scenarios) // 2
                            _fd_holdout_pool = _fd_all_scenarios[_fd_holdout_start:]
                            if len(_fd_holdout_pool) == 0:
                                _fd_holdout_pool = _fd_all_scenarios
                            _fd_scenario_count = min(250, len(_fd_holdout_pool))
                            _fd_scenario_idx = _fd_holdout_pool[
                                np.linspace(0, len(_fd_holdout_pool) - 1, _fd_scenario_count, dtype=int)
                            ]
'''
if old in text:
    text = text.replace(old, new, 1)
elif '_fd_holdout_start = len(_fd_all_scenarios) // 2' not in text:
    raise SystemExit('holdout anchor not found')

old2 = '''                            _fd_cash_cut = max(1, max(hi for lo, hi, prize in _fd_payout_tiers_roi if prize > 0))
'''
new2 = '''                            # Cash cutoff is the last PAID place that actually exists in this
                            # contest. Never let a payout ladder extending beyond field size turn
                            # CashRate into an automatic 100% result.
                            _fd_cash_cut = max(
                                1,
                                min(
                                    _fd_full_field_roi,
                                    max(hi for lo, hi, prize in _fd_payout_tiers_roi if prize > 0 and lo <= _fd_full_field_roi),
                                ),
                            )
'''
if old2 in text:
    text = text.replace(old2, new2, 1)
elif 'Cash cutoff is the last PAID place' not in text:
    raise SystemExit('cash anchor not found')

path.write_text(text)
print('patched FanDuel Full Roster holdout evaluation and cash cutoff')
