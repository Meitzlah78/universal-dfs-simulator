from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()
old = '''                        _fd_full_field_roi = int(\n                            _fd_roi_contest.get("field_size")\n                            or _fd_roi_contest.get("current_entries")\n                            or (len(opponent_df) + int(_fd_roi_contest.get("your_entries") or 1))\n                        )'''
new = '''                        # FanDuel's Hail Mary page shows current entries separately from\n                        # contest capacity. Final rankings/payouts must use the full contest\n                        # capacity (215,568), not the partially filled current-entry count.\n                        _fd_hail_mary_capacity = 215568\n                        _fd_reported_field_size = int(_fd_roi_contest.get("field_size") or 0)\n                        _fd_full_field_roi = max(_fd_hail_mary_capacity, _fd_reported_field_size)'''
if old not in text:
    if '_fd_hail_mary_capacity = 215568' not in text:
        raise SystemExit('Hail Mary field-size block not found')
else:
    text = text.replace(old, new, 1)
path.write_text(text)
print('FanDuel Hail Mary contest evaluation uses 215,568-entry capacity; continuing active FanDuel patch workflow.')
