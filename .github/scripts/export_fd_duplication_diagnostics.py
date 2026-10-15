from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()
old = '''            "Expected Net ($)", "Expected ROI (%)", "Estimated Full Field Rank",
        ]:'''
new = '''            "Expected Net ($)", "Expected ROI (%)", "Estimated Full Field Rank",
            "Exact Matches in Final Field", "Estimated Field Copies",
        ]:'''
if old not in text:
    if '"Exact Matches in Final Field", "Estimated Field Copies",' in text:
        print("Duplication diagnostics already wired into display/export source.")
    else:
        raise SystemExit("Expected FanDuel display metric block not found")
else:
    path.write_text(text.replace(old, new, 1))
    print("Wired duplication diagnostics into FanDuel portfolio display/export.")
