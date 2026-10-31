from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch anchor not found: {label}")
    text = text.replace(old, new, 1)


# FanDuel Single Game keeps the same MVP/FLEX rules and weighting. This only
# removes repeated Python scans from the FLEX hot loop.
replace_once(
'''            chosen_indices = []
            chosen = {}
            used = set()
''',
'''            chosen_indices = []
            chosen = {}
            used = set()
            fd_all_player_indices = np.arange(len(names), dtype=int)
''',
"FD Single Game player indices",
)

replace_once(
'''                    choices = np.asarray([
                        i for i in range(len(names))
                        if i not in used and salary + salaries[i] <= salary_max
                    ], dtype=int)
''',
'''                    if used:
                        unused_mask = ~np.isin(fd_all_player_indices, np.fromiter(used, dtype=int, count=len(used)))
                    else:
                        unused_mask = np.ones(len(fd_all_player_indices), dtype=bool)
                    choices = fd_all_player_indices[
                        unused_mask & (salary + salaries[fd_all_player_indices] <= salary_max)
                    ]
''',
"FD Single Game FLEX choices",
)

APP.write_text(text, encoding="utf-8")
print("Installed FanDuel Single Game vectorized FLEX builder optimization")
