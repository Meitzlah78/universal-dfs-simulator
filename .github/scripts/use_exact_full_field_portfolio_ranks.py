from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''                _sampled_greater = _greater_field + _greater_own
                _sampled_ties = _equal_field + _equal_own
                _rank_fraction = (_sampled_greater + 0.5 * _sampled_ties + 1.0) / (total_field + 1.0)
                _estimated_ranks = np.clip(
                    1.0 + _rank_fraction * (_portfolio_full_size - 1),
                    1.0,
                    float(_portfolio_full_size),
                )
                _estimated_tie_sizes = np.maximum(
                    1,
                    np.rint(
                        (_sampled_ties + 1.0) / (total_field + _portfolio_lineup_count + 1.0)
                        * _portfolio_full_size
                    ).astype(np.int64),
                )
                _tie_start = np.maximum(
                    1,
                    np.floor(_estimated_ranks - (_estimated_tie_sizes - 1) / 2.0).astype(np.int64),
                )
                _tie_end = np.minimum(
                    _portfolio_full_size,
                    _tie_start + _estimated_tie_sizes - 1,
                )
'''

new = '''                _sampled_greater = _greater_field + _greater_own
                _sampled_ties = _equal_field + _equal_own
                # contest_field_df is already expanded to the selected contest's
                # full opponent count. Do not scale its ranks to the full field a
                # second time. Use the exact simulated contest ranks directly.
                # A tie occupies ranks (entries ahead + 1) through that rank plus
                # every equal-scoring opponent/other portfolio entry.
                _tie_start = np.maximum(1, (_sampled_greater + 1).astype(np.int64))
                _estimated_tie_sizes = np.maximum(1, (_sampled_ties + 1).astype(np.int64))
                _tie_end = np.minimum(
                    _portfolio_full_size,
                    _tie_start + _estimated_tie_sizes - 1,
                )
'''

if new in text:
    print("Exact full-field portfolio rank scoring already applied.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Portfolio payouts now use exact ranks from the expanded full opponent field.")
else:
    raise SystemExit("Could not find portfolio rank scaling block")
