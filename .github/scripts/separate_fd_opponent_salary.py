from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()
old = '''                                    feasible = (\n                                        (candidate_salary + max_remaining >= fd_salary_range[0])\n                                        & (candidate_salary + min_remaining <= min(fd_salary_range[1], 60000))\n                                    )'''
new = '''                                    _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n                                    _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n                                    feasible = (\n                                        (candidate_salary + max_remaining >= _fd_opponent_salary_min)\n                                        & (candidate_salary + min_remaining <= _fd_opponent_salary_max)\n                                    )'''
if old not in text:
    if '_fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster"' not in text:
        raise SystemExit('feasibility block not found')
else:
    text = text.replace(old, new, 1)
old2 = '''                                choices = choices[\n                                    (candidate_salary >= fd_salary_range[0])\n                                    & (candidate_salary <= min(fd_salary_range[1], 60000))\n                                ]'''
new2 = '''                                _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n                                _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n                                choices = choices[\n                                    (candidate_salary >= _fd_opponent_salary_min)\n                                    & (candidate_salary <= _fd_opponent_salary_max)\n                                ]'''
if old2 not in text:
    if text.count('_fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster"') < 2:
        raise SystemExit('final slot block not found')
else:
    text = text.replace(old2, new2, 1)
old3 = '''                    if salary < fd_salary_range[0] or salary > fd_salary_range[1] or salary > 60000:\n                        continue'''
new3 = '''                    _fd_opponent_salary_min = 59000 if lineup_mode == "Full Roster" else fd_salary_range[0]\n                    _fd_opponent_salary_max = 60000 if lineup_mode == "Full Roster" else min(fd_salary_range[1], 60000)\n                    if salary < _fd_opponent_salary_min or salary > _fd_opponent_salary_max:\n                        continue'''
if old3 not in text:
    if 'if salary < _fd_opponent_salary_min or salary > _fd_opponent_salary_max:' not in text:
        raise SystemExit('final salary check not found')
else:
    text = text.replace(old3, new3, 1)
path.write_text(text)
print('Separated FanDuel Full Roster opponent salary range from user slider.')
