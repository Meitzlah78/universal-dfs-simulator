from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
old = '''        if "Salary" in fd_display.columns:
            fd_display_columns.append("Salary")
        fd_display_columns = list(dict.fromkeys(
            col for col in fd_display_columns if col in fd_display.columns
        ))
'''
new = '''        if "Salary" in fd_display.columns:
            fd_display_columns.append("Salary")
        # FanDuel contest comparison already calculates these metrics. Keep them
        # visible in the post-SIM portfolio table so the completed contest run is
        # not reduced back to only projection/score/salary after st.rerun().
        for metric_col in [
            "ContestScore", "WinRate", "Top1", "Top5", "Top10", "CashRate",
            "AvgPercentile", "Entry Fee ($)", "Expected Prize ($)",
            "Expected Net ($)", "Expected ROI (%)", "Estimated Full Field Rank",
        ]:
            if metric_col in fd_display.columns:
                fd_display_columns.append(metric_col)
        fd_display_columns = list(dict.fromkeys(
            col for col in fd_display_columns if col in fd_display.columns
        ))
'''
if old not in text:
    raise SystemExit("FanDuel display block not found; refusing to patch")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("Patched FanDuel contest metrics into post-SIM display")
