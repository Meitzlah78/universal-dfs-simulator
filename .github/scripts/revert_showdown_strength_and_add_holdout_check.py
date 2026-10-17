from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

strong = '''        # Public Showdown fields are ownership-driven, but they are not six fully
        # independent ownership draws. Better players tend to construct lineups that
        # use the salary cap efficiently. Keep contrarian salary left on the table,
        # but make weak constructions progressively less common.
        salary_left = max(0, int(salary_cap - salary))
        if salary_left > 500:
            salary_acceptance = float(np.exp(-(salary_left - 500) / 7000.0))
            if rng.random() > salary_acceptance:
                continue

        # Add a mild lineup-strength filter using the same simulation means that are
        # already available to the opponent generator. This is deliberately much
        # softer than the user's candidate optimizer: it only removes a portion of
        # obviously weak public constructions while ownership remains the main draw.
        lineup_mean = float(means[picked].sum() + means[captain_idx] * 0.5)
        pool_mean = float(np.mean(means)) if len(means) else 0.0
        baseline_mean = max(0.01, pool_mean * 6.5)
        strength_ratio = lineup_mean / baseline_mean
        if strength_ratio < 1.0:
            strength_acceptance = float(np.clip(0.35 + 0.65 * strength_ratio, 0.35, 1.0))
            if rng.random() > strength_acceptance:
                continue
'''

original = '''        # Completed large-field Showdown contests show that the public field is not
        # six random legal players. Most entries use a meaningful amount of the cap,
        # while low-salary constructions still exist as a smaller contrarian tail.
        # Keep those low-salary lineups possible, but make them progressively rarer.
        # This strengthens the simulated public field without making it use the same
        # ceiling/leverage optimizer as SIMMAH's candidate builder.
        if salary < 40000:
            low_salary_acceptance = float(np.exp((salary - 40000) / 4000.0))
            if rng.random() > low_salary_acceptance:
                continue
'''

if strong in text:
    text = text.replace(strong, original, 1)
elif original not in text:
    raise SystemExit("Could not find Showdown opponent strength block")

needle = '''    results_df["AvgPercentile"] = avg_percentiles / selection_n_sims
'''
insert = '''    results_df["AvgPercentile"] = avg_percentiles / selection_n_sims

    # Diagnostic only: show whether the selected candidates keep their advantage
    # on the untouched second half of simulations. A large drop from Selection to
    # Holdout points to selection overfitting rather than a weak opponent field.
    if holdout_n_sims > 0 and n_candidates > 0:
        _diag_count = min(20, n_candidates)
        _diag_idx = np.arange(_diag_count, dtype=np.int32)
        _diag_candidate_idx = candidate_idx[_diag_idx]
        _diag_top1 = np.zeros(_diag_count, dtype=np.float64)
        _diag_top5 = np.zeros(_diag_count, dtype=np.float64)
        _diag_top10 = np.zeros(_diag_count, dtype=np.float64)
        _diag_cash = np.zeros(_diag_count, dtype=np.float64)
        _diag_pct = np.zeros(_diag_count, dtype=np.float64)
        _diag_batch_size = 128
        for _diag_start in range(holdout_start, n_sims, _diag_batch_size):
            _diag_end = min(_diag_start + _diag_batch_size, n_sims)
            _diag_values = simulation_values[_diag_start:_diag_end]
            _diag_scores = _diag_values[:, _diag_candidate_idx].sum(axis=2)
            _diag_field_scores = _diag_values[:, contest_idx].sum(axis=2)
            if scoring_multiplier != 1.0:
                _diag_scores[:, :] += _diag_values[:, _diag_candidate_idx[:, 0]] * (scoring_multiplier - 1.0)
                _diag_field_scores[:, :] += _diag_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)
            _diag_sorted = np.sort(_diag_field_scores, axis=1)
            _diag_greater = np.empty_like(_diag_scores, dtype=np.float64)
            for _r in range(_diag_scores.shape[0]):
                _diag_greater[_r] = total_field - np.searchsorted(_diag_sorted[_r], _diag_scores[_r], side="right")
            _diag_percentiles = 1.0 - (_diag_greater / max(1, total_field))
            _diag_top1 += np.sum(_diag_percentiles >= 0.99, axis=0)
            _diag_top5 += np.sum(_diag_percentiles >= 0.95, axis=0)
            _diag_top10 += np.sum(_diag_percentiles >= 0.90, axis=0)
            _diag_cash += np.sum(_diag_percentiles >= 0.50, axis=0)
            _diag_pct += np.sum(_diag_percentiles, axis=0)
        _selection_slice = results_df.iloc[:_diag_count] if "results_df" in locals() else None
        st.session_state["contest_holdout_diagnostic"] = {
            "lineups": int(_diag_count),
            "holdout_sims": int(holdout_n_sims),
            "top1": float(np.mean(_diag_top1 / holdout_n_sims)),
            "top5": float(np.mean(_diag_top5 / holdout_n_sims)),
            "top10": float(np.mean(_diag_top10 / holdout_n_sims)),
            "cash": float(np.mean(_diag_cash / holdout_n_sims)),
            "avg_percentile": float(np.mean(_diag_pct / holdout_n_sims)),
        }
'''

if 'contest_holdout_diagnostic' not in text:
    if needle not in text:
        raise SystemExit("Could not find Contest Sim results insertion point")
    text = text.replace(needle, insert, 1)

path.write_text(text, encoding="utf-8")
print("Reverted opponent strength tweak and added holdout diagnostic.")
