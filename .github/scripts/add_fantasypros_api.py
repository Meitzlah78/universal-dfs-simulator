from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text(encoding="utf-8")

old = '''            if projection_week is None:
                now_et = datetime.now(ZoneInfo("America/New_York"))
                season_start = datetime(season, 9, 13, tzinfo=ZoneInfo("America/New_York"))
                projection_week = max(1, min(18, ((now_et.date() - season_start.date()).days // 7) + 1))
'''
new = '''            if projection_week is None:
                now_et = datetime.now(ZoneInfo("America/New_York"))
                # NFL Week 1 begins with the Thursday immediately after Labor Day.
                # The old fallback anchored to the first Sunday, which left the app
                # one week behind during the Thursday-Saturday portion of each week
                # (for example DAL-GB on 2026-10-18 was incorrectly requested as
                # Week 5 instead of Week 6).
                sep1 = datetime(season, 9, 1, tzinfo=ZoneInfo("America/New_York"))
                labor_day = sep1 + pd.Timedelta(days=(7 - sep1.weekday()) % 7)
                kickoff = labor_day + pd.Timedelta(days=3)
                projection_week = max(1, min(18, ((now_et.date() - kickoff.date()).days // 7) + 1))
'''
if old not in s:
    if 'NFL Week 1 begins with the Thursday immediately after Labor Day' in s:
        print("FantasyPros NFL week calculation already fixed")
        raise SystemExit(0)
    raise SystemExit("FantasyPros fallback week block not found")
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("FantasyPros NFL week calculation fixed")
