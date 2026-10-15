from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

anchor = '''        rng = np.random.default_rng(123)\n        opponent_rows = []\n        attempts = 0\n'''
replacement = '''        rng = np.random.default_rng(123)\n        opponent_rows = []\n        attempts = 0\n        # Opponent salary bounds are fixed for FanDuel Full Roster and independent\n        # of the user's lineup salary range. Compute them once per field build.\n        _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n        _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n'''
if anchor not in text:
    raise SystemExit("opponent field setup anchor not found")
text = text.replace(anchor, replacement, 1)

repeated = '''                                    _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n                                    _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n'''
if text.count(repeated) != 2:
    raise SystemExit(f"expected 2 indented salary-bound blocks, found {text.count(repeated)}")
text = text.replace(repeated, "", 2)

final_repeated = '''                    _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n                    _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n'''
if text.count(final_repeated) != 1:
    raise SystemExit(f"expected 1 final salary-bound block, found {text.count(final_repeated)}")
text = text.replace(final_repeated, "", 1)

path.write_text(text)
