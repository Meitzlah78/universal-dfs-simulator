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
            # DFF's FanDuel all-slate projection feed contains the same NFL
            # fantasy-point projections and, unlike the generic single-game
            # page, exposes every matchup. target_names below selects the
            # salary-file game by player-name intersection.
            url = (
                "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/"
                if site == "draftkings"
                else "https://www.dailyfantasyfuel.com/nfl/projections/fanduel/"
            )
'''

if old not in text:
    if 'else "https://www.dailyfantasyfuel.com/nfl/projections/fanduel/"' in text:
        print('FanDuel single-game DFF feed already patched')
    else:
        raise SystemExit('DFF single-game URL block not found')
else:
    text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
print('Patched FanDuel single-game DFF feed to all-slate projections')
