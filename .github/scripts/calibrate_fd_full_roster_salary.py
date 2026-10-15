from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old = '''            value=(57000, 60000) if lineup_mode == "Full Roster" else (54000, 60000),'''
new = '''            # Real FanDuel NFL large-field data is heavily concentrated near the cap.
            # Default Full Roster builds to the range containing ~97% of observed entries.
            value=(59000, 60000) if lineup_mode == "Full Roster" else (54000, 60000),'''
if old not in text:
    if new not in text:
        raise SystemExit("salary slider anchor not found")
else:
    text = text.replace(old, new, 1)

old2 = '''                    if salary < fd_salary_range[0] or salary > fd_salary_range[1] or salary > 60000:
                        continue
                    key = tuple(chosen[slot] for slot in fd_slots)'''
new2 = '''                    if salary < fd_salary_range[0] or salary > fd_salary_range[1] or salary > 60000:
                        continue
                    # Calibrate FanDuel NFL Full Roster salary usage to observed large-field
                    # contest behavior. In a 568k-entry historical contest the average salary
                    # was about $59,781, 41% used the full $60k, 91% used >=$59.5k, and 97%
                    # used >=$59k. The sequential player picker otherwise overproduces cheap
                    # lineups, so use an acceptance curve after a legal lineup is assembled.
                    # This changes opponent construction only; Single Game and DraftKings are untouched.
                    if lineup_mode == "Full Roster":
                        _fd_salary_accept = {
                            60000: 1.00,
                            59900: 0.90,
                            59800: 0.72,
                            59700: 0.58,
                            59600: 0.46,
                            59500: 0.36,
                            59400: 0.24,
                            59300: 0.18,
                            59200: 0.13,
                            59100: 0.09,
                            59000: 0.06,
                        }.get(int(salary), 0.01 if salary >= 58000 else 0.002)
                        if rng.random() > _fd_salary_accept:
                            continue
                    key = tuple(chosen[slot] for slot in fd_slots)'''
if old2 not in text:
    if "_fd_salary_accept = {" not in text:
        raise SystemExit("opponent acceptance anchor not found")
else:
    text = text.replace(old2, new2, 1)

path.write_text(text)
print("Patched FanDuel Full Roster salary calibration")
