from pathlib import Path

# The contest-metric truth fix is already present in dfs_app.py.
# Reuse this existing, trusted workflow trigger to apply the pending
# FanDuel Full Roster salary calibration patch.
patch = Path('.github/scripts/calibrate_fd_full_roster_salary.py')
if not patch.exists():
    raise SystemExit('FanDuel salary calibration patch not found')
exec(compile(patch.read_text(), str(patch), 'exec'))
