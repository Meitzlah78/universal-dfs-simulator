from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old = '''    if platform == "DraftKings" and lineup_mode == "Classic":
        lineup_cols = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
        scoring_multiplier = 1.0
    else:
        lineup_cols = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        scoring_multiplier = 1.5
'''
new = old + '''    is_dk_showdown = platform == "DraftKings" and lineup_mode != "Classic"
'''
if old not in text:
    raise SystemExit("lineup mode anchor not found")
text = text.replace(old, new, 1)

text = text.replace(
    'if scoring_multiplier == 1.5 and candidate_idx.shape[1] == 6:',
    'if is_dk_showdown:',
    1,
)
text = text.replace(
    'if scoring_multiplier == 1.5 and _diag_candidate_idx.shape[1] == 6:',
    'if is_dk_showdown:',
    1,
)

main_old = '''        else:
            # Preserve the existing generic full-roster scoring path.
            batch_candidate_scores = batch_values[:, candidate_idx].sum(axis=2)
            batch_field_scores = batch_values[:, contest_idx].sum(axis=2)
'''
main_new = '''        else:
            # Preserve generic non-DK scoring, including any captain multiplier.
            batch_candidate_scores = batch_values[:, candidate_idx].sum(axis=2)
            batch_field_scores = batch_values[:, contest_idx].sum(axis=2)
            if scoring_multiplier != 1.0:
                batch_candidate_scores += batch_values[:, candidate_idx[:, 0]] * (scoring_multiplier - 1.0)
                batch_field_scores += batch_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)
'''
if main_old not in text:
    raise SystemExit("main fallback anchor not found")
text = text.replace(main_old, main_new, 1)

diag_old = '''            else:
                _diag_scores = _diag_values[:, _diag_candidate_idx].sum(axis=2)
                _diag_field_scores = _diag_values[:, contest_idx].sum(axis=2)
'''
diag_new = '''            else:
                _diag_scores = _diag_values[:, _diag_candidate_idx].sum(axis=2)
                _diag_field_scores = _diag_values[:, contest_idx].sum(axis=2)
                if scoring_multiplier != 1.0:
                    _diag_scores += _diag_values[:, _diag_candidate_idx[:, 0]] * (scoring_multiplier - 1.0)
                    _diag_field_scores += _diag_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)
'''
if diag_old not in text:
    raise SystemExit("diagnostic fallback anchor not found")
text = text.replace(diag_old, diag_new, 1)

path.write_text(text)
print("Restricted DK engine scoring to DraftKings Showdown and restored generic multiplier fallbacks")
