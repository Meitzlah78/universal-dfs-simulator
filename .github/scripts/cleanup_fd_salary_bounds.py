from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

anchor = '''        rng = np.random.default_rng(123)\n        opponent_rows = []\n        attempts = 0\n'''
replacement = '''        rng = np.random.default_rng(123)\n        opponent_rows = []\n        attempts = 0\n        # Opponent salary bounds are fixed for FanDuel Full Roster and independent\n        # of the user's lineup salary range. Compute them once per field build.\n        _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n        _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n'''
if text.count(anchor) != 1:
    raise SystemExit(f"expected 1 opponent field setup anchor, found {text.count(anchor)}")
text = text.replace(anchor, replacement, 1)

blocks = [
'''                                    _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n                                    _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n''',
'''                    _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n                    _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n''',
]
for block in blocks:
    count = text.count(block)
    if count != 1:
        raise SystemExit(f"expected 1 salary-bound block at this indentation, found {count}")
    text = text.replace(block, "", 1)

path.write_text(text)
