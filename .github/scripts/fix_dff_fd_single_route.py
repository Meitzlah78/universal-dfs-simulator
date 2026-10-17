from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()
old = '''            for slate_date in recent_dates:
                # DFF FanDuel single-game slate URLs are exposed on /nfl with
                # platform=fd and a slate id.  The current DAL @ GB slate is 21128.
                # Try the explicit slate page first; target-name overlap still
                # protects against returning it for an unrelated salary file.
                page_url = (
                    "https://www.dailyfantasyfuel.com/nfl?platform=fd&slate=21128"
                    if slate_date == "2026-10-18"
                    else f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}/"
                )
                page = requests.get(
                    page_url,
                    headers=headers_direct, timeout=30
                )
'''
new = '''            for slate_date in recent_dates:
                # Use DFF's actual FanDuel Single Game projection route. Never
                # parse the /nfl optimizer page here; it may be a JS shell with
                # no HTML projection table. Target-name overlap below selects
                # the matching game instead of hardcoding a slate identifier.
                page_url = f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}/"
                page = requests.get(
                    page_url,
                    headers=headers_direct, timeout=30
                )
'''
if old not in text:
    raise SystemExit('expected DFF hardcoded route block not found')
text = text.replace(old, new, 1)
old2 = '''                "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/"
                if site == "draftkings"
                else "https://www.dailyfantasyfuel.com/nfl/projections/fanduel/"
'''
new2 = '''                "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/"
                if site == "draftkings"
                else "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/"
'''
if old2 not in text:
    raise SystemExit('expected generic FanDuel single-game route block not found')
text = text.replace(old2, new2, 1)
path.write_text(text)
print('updated DFF FanDuel Single Game routes')
