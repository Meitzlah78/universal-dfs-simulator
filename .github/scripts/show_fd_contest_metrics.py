from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''        if "Salary" in fd_display.columns:
            fd_display_columns.append("Salary")
        fd_display_columns = list(dict.fromkeys(
            col for col in fd_display_columns if col in fd_display.columns
        ))
'''

new = '''        if "Salary" in fd_display.columns:
            fd_display_columns.append("Salary")
        # Keep the completed FanDuel contest-simulation metrics visible after the
        # post-SIM rerun. Previously fd_rank_source contained these values, but the
        # display column whitelist hid them and made the refreshed table look like
        # a plain lineup export.
        for contest_col in [
            "Win %", "Top 1%", "Top 5%", "Top 10%", "Cash %",
            "Average Percentile", "Expected Prize ($)", "Expected Net ($)",
            "Expected ROI (%)"
        ]:
            if contest_col in fd_display.columns:
                fd_display_columns.append(contest_col)
        fd_display_columns = list(dict.fromkeys(
            col for col in fd_display_columns if col in fd_display.columns
        ))
'''

if new in s:
    print("FanDuel contest metrics display already applied")
    raise SystemExit(0)

count = s.count(old)
if count != 1:
    raise SystemExit(f"Expected exactly one FanDuel display marker, found {count}")

p.write_text(s.replace(old, new, 1))
print("Applied FanDuel contest metrics display patch")
