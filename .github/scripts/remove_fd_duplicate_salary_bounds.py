from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()
block = '''                                _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n                                _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n                                choices = choices[\n'''
replacement = '''                                choices = choices[\n'''
count = text.count(block)
if count != 1:
    raise SystemExit(f"expected exactly one duplicate salary-bound block, found {count}")
text = text.replace(block, replacement, 1)
path.write_text(text)
