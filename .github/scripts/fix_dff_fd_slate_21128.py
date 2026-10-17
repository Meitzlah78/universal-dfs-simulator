from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''                page = requests.get(
                    f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}/",
                    headers=headers_direct, timeout=30
                )'''
new='''                # DFF FanDuel single-game slate URLs are exposed on /nfl with
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
                )'''
if old not in s: raise SystemExit('direct request block not found')
s=s.replace(old,new,1)
p.write_text(s)
print('DFF FD DAL-GB uses supplied slate 21128 URL')
