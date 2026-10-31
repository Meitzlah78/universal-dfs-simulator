from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''                page = requests.get(
                    f"https://www.dailyfantasyfuel.com/nfl/projections/fanduel/{slate_date}/",
                    headers=headers_direct, timeout=30
                )'''
new='''                page = requests.get(
                    f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}/",
                    headers=headers_direct, timeout=30
                )'''
if old not in s:
    raise SystemExit('direct FanDuel dated-page block not found')
s=s.replace(old,new,1)
p.write_text(s)
print('DFF FanDuel Single Game now uses showdown-single-game-projections/fanduel dated pages')
