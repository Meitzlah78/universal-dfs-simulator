from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

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

old_comment = '''            # DFF's FanDuel all-slate projection feed contains the same NFL
            # fantasy-point projections and, unlike the generic single-game
            # page, exposes every matchup. target_names below selects the
            # salary-file game by player-name intersection.
'''
new_comment = '''            # FanDuel's generic page can point at a different slate. The
            # slate-discovery fallback below resolves the actual date + slate
            # identifier and matches it against the uploaded salary names.
'''
if old_comment in text:
    text = text.replace(old_comment, new_comment, 1)

old_base = '''                for slate_date, slate_code in candidates:
                    base = (
                        f"https://www.dailyfantasyfuel.com/nfl/"
                        f"showdown-single-game-projections/{site}/{slate_date}"
                    )
                    candidate_urls = []
                    if slate_code:
                        encoded = quote(slate_code, safe='')
                        candidate_urls.extend([
                            f"{base}?slate={encoded}",
                            f"{base}?url={encoded}",
                        ])
                    candidate_urls.append(base + '/')
'''
new_base = '''                for slate_date, slate_code in candidates:
                    # DFF's FanDuel slate URLs use the regular projections route,
                    # e.g. /nfl/projections/fanduel/YYYY-MM-DD?slate=SLATE_ID.
                    # The old code incorrectly tried the showdown route and could
                    # never reach a valid FD slate such as DAL-GB.
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
                    if slate_code:
                        encoded = quote(slate_code, safe='')
                        candidate_urls.extend([
                            f"{base}?slate={encoded}",
                            f"{base}?url={encoded}",
                        ])
                    candidate_urls.append(base + '/')
'''
if old_base in text:
    text = text.replace(old_base, new_base, 1)
elif "f\"projections/fanduel/{slate_date}\"" not in text:
    raise SystemExit('DFF slate candidate URL block not found')

path.write_text(text, encoding='utf-8')
print('Patched FanDuel DFF slate URLs to date + slate ID projections route')
