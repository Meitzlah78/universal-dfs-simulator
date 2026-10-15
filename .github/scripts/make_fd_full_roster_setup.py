from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

# The $45K Sun NFL Hail Mary has a 215,568-entry field. 65,000 is only the
# last PAID place in the supplied payout ladder, not the contest field size.
# Treating 65,000 as the whole field made every lineup appear to cash.
old = '_fd_full_field_roi = int(_fd_roi_contest.get("field_size") or _fd_roi_contest.get("current_entries") or 65000)'
new = '_fd_full_field_roi = int(_fd_roi_contest.get("field_size") or _fd_roi_contest.get("max_entries") or _fd_roi_contest.get("current_entries") or 215568)'

if old in s:
    s = s.replace(old, new, 1)
    p.write_text(s)
    print("Fixed FanDuel Hail Mary field size: 215,568 total entries; 65,000 paid places")
elif new in s:
    print("FanDuel Hail Mary full-field fix already applied")
else:
    raise SystemExit("FanDuel Hail Mary field-size line not found")
