from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()

old_import = '''    duplicate_expansion_weights as dk_duplicate_expansion_weights,\n    sample_opponent_batch as dk_sample_opponent_batch,\n    score_lineup_matrix as dk_score_lineup_matrix,'''
new_import = '''    duplicate_expansion_weights as dk_duplicate_expansion_weights,\n    opponent_lineup_means as dk_opponent_lineup_means,\n    opponent_quality_acceptance as dk_opponent_quality_acceptance,\n    sample_opponent_batch as dk_sample_opponent_batch,\n    score_lineup_matrix as dk_score_lineup_matrix,'''
if old_import not in text:
    raise SystemExit('DK import anchor not found')
text = text.replace(old_import, new_import, 1)

old_captain = '''    captain_weights = np.clip(captain_base_weights, 0.01, None)\n    # Completed large-field DK Showdown data is materially more concentrated at\n    # Captain than a straight ownership draw. BUF@LAR put about 59.7% of entries\n    # on its top four Captains. Sharpen Captain only; FLEX remains ownership-first.\n    captain_weights = np.power(captain_weights, 1.45)\n    captain_weights /= captain_weights.sum()'''
new_captain = '''    captain_weights = np.clip(captain_base_weights, 0.01, None)\n    # External Field CPT Own % is already role-specific. Only sharpen the fallback\n    # curve when no usable external Captain ownership exists.\n    if not has_external_captain_ownership:\n        captain_weights = np.power(captain_weights, 1.45)\n    captain_weights /= captain_weights.sum()'''
if old_captain not in text:
    raise SystemExit('Captain weighting anchor not found')
text = text.replace(old_captain, new_captain, 1)

old_valid = '''        salary_draw = rng.random(n)\n        valid = np.flatnonzero(\n            (salary_batch <= salary_cap)\n            & (salary_batch >= 45000)\n            & multi_team\n            & (salary_draw <= salary_acceptance)\n        )'''
new_valid = '''        salary_draw = rng.random(n)\n        lineup_means = dk_opponent_lineup_means(captain_batch, flex_batch, means)\n        quality_acceptance = dk_opponent_quality_acceptance(lineup_means)\n        quality_draw = rng.random(n)\n        valid = np.flatnonzero(\n            (salary_batch <= salary_cap)\n            & (salary_batch >= 45000)\n            & multi_team\n            & (salary_draw <= salary_acceptance)\n            & (quality_draw <= quality_acceptance)\n        )'''
if old_valid not in text:
    raise SystemExit('Opponent acceptance anchor not found')
text = text.replace(old_valid, new_valid, 1)

path.write_text(text)
