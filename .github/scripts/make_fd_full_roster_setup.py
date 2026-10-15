from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# Score the FanDuel contest comparison in batches with four workers so the
# contest step follows the same parallel-work pattern used by DK.
needle = '''                        scores = opponent_df["ProjectedPoints"].to_numpy(dtype=float)
                        compared = add_lineup_field_ownership(user_lineups.copy())
                        compared["BeatsOpponents"] = compared["ProjectedPoints"].apply(lambda score: int(np.sum(scores < float(score))))
                        compared["FieldPercentile"] = compared["ProjectedPoints"].apply(lambda score: round(100.0 * np.mean(scores <= float(score)), 1))
                        compared["FieldRank"] = compared["ProjectedPoints"].apply(lambda score: 1 + int(np.sum(scores > float(score))))
                        compared = add_field_ranking_metrics(compared, scores)
'''
replacement = '''                        scores = opponent_df["ProjectedPoints"].to_numpy(dtype=float)
                        compared = add_lineup_field_ownership(user_lineups.copy())
                        if lineup_mode == "Full Roster" and len(compared) > 0:
                            _fd_score_values = pd.to_numeric(compared["ProjectedPoints"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
                            _fd_batch_count = min(4, len(_fd_score_values))
                            _fd_batches = [batch for batch in np.array_split(np.arange(len(_fd_score_values)), _fd_batch_count) if len(batch)]

                            def _fd_score_batch(indices):
                                batch_scores = _fd_score_values[indices]
                                beats = np.asarray([int(np.sum(scores < score)) for score in batch_scores], dtype=int)
                                percentiles = np.asarray([round(100.0 * np.mean(scores <= score), 1) for score in batch_scores], dtype=float)
                                ranks = np.asarray([1 + int(np.sum(scores > score)) for score in batch_scores], dtype=int)
                                return indices, beats, percentiles, ranks

                            _fd_beats = np.zeros(len(_fd_score_values), dtype=int)
                            _fd_percentiles = np.zeros(len(_fd_score_values), dtype=float)
                            _fd_ranks = np.ones(len(_fd_score_values), dtype=int)
                            with ThreadPoolExecutor(max_workers=4) as _fd_executor:
                                _fd_futures = [_fd_executor.submit(_fd_score_batch, batch) for batch in _fd_batches]
                                for _fd_future in as_completed(_fd_futures):
                                    _fd_indices, _fd_b, _fd_p, _fd_r = _fd_future.result()
                                    _fd_beats[_fd_indices] = _fd_b
                                    _fd_percentiles[_fd_indices] = _fd_p
                                    _fd_ranks[_fd_indices] = _fd_r
                            compared["BeatsOpponents"] = _fd_beats
                            compared["FieldPercentile"] = _fd_percentiles
                            compared["FieldRank"] = _fd_ranks
                        else:
                            compared["BeatsOpponents"] = compared["ProjectedPoints"].apply(lambda score: int(np.sum(scores < float(score))))
                            compared["FieldPercentile"] = compared["ProjectedPoints"].apply(lambda score: round(100.0 * np.mean(scores <= float(score)), 1))
                            compared["FieldRank"] = compared["ProjectedPoints"].apply(lambda score: 1 + int(np.sum(scores > float(score))))
                        compared = add_field_ranking_metrics(compared, scores)
'''
if needle not in text:
    raise SystemExit("FanDuel contest scoring block not found")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
