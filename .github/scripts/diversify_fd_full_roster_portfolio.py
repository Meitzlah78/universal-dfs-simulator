from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
old = '''                        # Choose the final entry set without using ROI itself. This avoids
                        # selecting on the same payout results we are trying to measure.
                        _fd_select_metric = "ContestScore" if "ContestScore" in compared.columns else "ProjectedPoints"
                        _fd_selected_idx = (
                            compared[_fd_select_metric].astype(float)
                            .nlargest(_fd_my_entries_roi).index.to_numpy(dtype=int)
                        )
'''
new = '''                        # Choose the final entry set without using holdout ROI itself. For
                        # FanDuel Full Roster, build a portfolio instead of blindly taking the
                        # top N rows: retain lineup strength while penalizing near-identical
                        # rosters so one simulated construction cannot dominate all entries.
                        _fd_select_metric = "ContestScore" if "ContestScore" in compared.columns else "ProjectedPoints"
                        if lineup_mode == "Full Roster" and _fd_my_entries_roi > 1:
                            _fd_base = pd.to_numeric(compared[_fd_select_metric], errors="coerce").fillna(-np.inf).to_numpy(dtype=float)
                            _fd_order = np.argsort(-_fd_base, kind="stable")
                            _fd_candidate_cap = min(len(_fd_order), max(500, _fd_my_entries_roi * 50))
                            _fd_pool_idx = _fd_order[:_fd_candidate_cap]
                            _fd_finite = _fd_base[_fd_pool_idx][np.isfinite(_fd_base[_fd_pool_idx])]
                            if len(_fd_finite) > 1 and float(np.max(_fd_finite)) > float(np.min(_fd_finite)):
                                _fd_strength = (_fd_base - float(np.min(_fd_finite))) / (float(np.max(_fd_finite)) - float(np.min(_fd_finite)))
                            else:
                                _fd_strength = np.zeros(len(compared), dtype=float)
                            _fd_rosters = [frozenset(str(compared.iloc[i][slot]) for slot in fd_slots if slot in compared.columns) for i in range(len(compared))]
                            _fd_chosen = []
                            _fd_remaining = set(int(i) for i in _fd_pool_idx)
                            while _fd_remaining and len(_fd_chosen) < _fd_my_entries_roi:
                                _fd_best_i = None
                                _fd_best_score = -np.inf
                                for _fd_i in _fd_remaining:
                                    if _fd_chosen:
                                        _fd_max_overlap = max(len(_fd_rosters[_fd_i] & _fd_rosters[_fd_j]) / max(len(_fd_rosters[_fd_i]), 1) for _fd_j in _fd_chosen)
                                    else:
                                        _fd_max_overlap = 0.0
                                    # A modest overlap penalty diversifies the portfolio without
                                    # discarding strong lineups. It affects Full Roster only.
                                    _fd_portfolio_score = float(_fd_strength[_fd_i]) - 0.12 * (_fd_max_overlap ** 2)
                                    if _fd_portfolio_score > _fd_best_score:
                                        _fd_best_score = _fd_portfolio_score
                                        _fd_best_i = _fd_i
                                if _fd_best_i is None:
                                    break
                                _fd_chosen.append(_fd_best_i)
                                _fd_remaining.remove(_fd_best_i)
                            _fd_selected_idx = np.asarray(_fd_chosen, dtype=int)
                        else:
                            _fd_selected_idx = (
                                compared[_fd_select_metric].astype(float)
                                .nlargest(_fd_my_entries_roi).index.to_numpy(dtype=int)
                            )
'''
if new in text:
    print("FanDuel portfolio diversification already applied.")
elif old not in text:
    raise SystemExit("Expected FanDuel final-entry selection block not found")
else:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Applied FanDuel Full Roster portfolio diversification.")
