from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

# FanDuel single-game slate URL routing.
old = '''        if is_single_game:
            # This is the working Colab route; DraftKings is the default view.
            url = (
                "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/"
                if site == "draftkings"
                else "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/"
            )
'''
new = '''        if is_single_game:
            # FanDuel's generic page can point at a different slate. The
            # slate-discovery fallback below resolves the actual date + slate
            # identifier and matches it against the uploaded salary names.
            url = (
                "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/"
                if site == "draftkings"
                else "https://www.dailyfantasyfuel.com/nfl/projections/fanduel/"
            )
'''
if old in text:
    text = text.replace(old, new, 1)

old_base = '''                for slate_date, slate_code in candidates:
                    base = (
                        f"https://www.dailyfantasyfuel.com/nfl/"
                        f"showdown-single-game-projections/{site}/{slate_date}"
                    )
                    candidate_urls = []
'''
new_base = '''                for slate_date, slate_code in candidates:
                    if site == 'fanduel':
                        base = (
                            f"https://www.dailyfantasyfuel.com/nfl/"
                            f"projections/fanduel/{slate_date}"
                        )
                    else:
                        base = (
                            f"https://www.dailyfantasyfuel.com/nfl/"
                            f"showdown-single-game-projections/{site}/{slate_date}"
                        )
                    candidate_urls = []
'''
if old_base in text:
    text = text.replace(old_base, new_base, 1)

# DFF now returns a 3-level MultiIndex table. pd.read_html has already consumed
# those header rows, so iloc[3:] incorrectly discards three real players. Also,
# the useful labels (NAME, FD FP PROJECTED, etc.) are usually in the middle
# level while the final level is just Unnamed:*.
old_flatten = '''            if isinstance(dff_table.columns, pd.MultiIndex):
                dff_table = dff_table.iloc[3:].copy()
                dff_table.columns = [
                    str(col[-1]).strip() if isinstance(col, tuple) else str(col).strip()
                    for col in dff_table.columns
                ]
'''
new_flatten = '''            if isinstance(dff_table.columns, pd.MultiIndex):
                def _dff_header(col):
                    parts = [str(part).strip() for part in col]
                    useful = [
                        part for part in parts
                        if part and not part.casefold().startswith("unnamed:")
                    ]
                    # Prefer the most specific useful header level. On the
                    # current DFF table this yields NAME and FD FP PROJECTED.
                    return useful[-1] if useful else parts[-1]
                dff_table.columns = [_dff_header(col) for col in dff_table.columns]
'''
if old_flatten in text:
    text = text.replace(old_flatten, new_flatten, 1)
elif 'def _dff_header(col):' not in text:
    raise SystemExit('Primary DFF MultiIndex parser block not found')

old_candidate_flatten = '''                        if isinstance(candidate_table.columns, pd.MultiIndex):
                            candidate_table = candidate_table.iloc[3:].copy()
                            candidate_table.columns = [
                                str(col[-1]).strip() if isinstance(col, tuple) else str(col).strip()
                                for col in candidate_table.columns
                            ]
'''
new_candidate_flatten = '''                        if isinstance(candidate_table.columns, pd.MultiIndex):
                            def _dff_candidate_header(col):
                                parts = [str(part).strip() for part in col]
                                useful = [
                                    part for part in parts
                                    if part and not part.casefold().startswith("unnamed:")
                                ]
                                return useful[-1] if useful else parts[-1]
                            candidate_table.columns = [
                                _dff_candidate_header(col) for col in candidate_table.columns
                            ]
'''
text = text.replace(old_candidate_flatten, new_candidate_flatten)

path.write_text(text, encoding='utf-8')
print('Patched DFF FanDuel slate URLs and current MultiIndex table parsing')
