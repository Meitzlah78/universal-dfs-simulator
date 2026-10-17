"""Expose Projected Dupes in the actual DK Showdown portfolio/export path."""
from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

old = '''        "Salary", "Lineup Ownership Score (%)", "ContestScore", "WinRate", "Top1", "Top5",\n'''
new = '''        "Salary", "Lineup Ownership Score (%)", "Projected Dupes", "ContestScore", "WinRate", "Top1", "Top5",\n'''
if new not in text:
    if old not in text:
        raise SystemExit("portfolio export column anchor not found")
    text = text.replace(old, new)

anchor = '''    st.session_state["portfolio_df"] = portfolio_df\n    portfolio_export_df = portfolio_df[\n'''
injection = '''    # Pre-lock exact-lineup popularity estimate. Keep this separate from the\n    # summed Lineup Ownership Score and do not use it as a hidden diversity rule.\n    if not classic_mode and "Captain" in portfolio_df.columns:\n        _dupe_ownership_df = st.session_state.get("latest_field_ownership")\n        _dupe_own = {}\n        if isinstance(_dupe_ownership_df, pd.DataFrame) and not _dupe_ownership_df.empty and "Name" in _dupe_ownership_df.columns:\n            _dupe_own = dict(zip(\n                _dupe_ownership_df["Name"].astype(str),\n                pd.to_numeric(_dupe_ownership_df.get("Ownership %", 0.0), errors="coerce").fillna(0.0) / 100.0\n            ))\n        _dupe_field_size = int(max(2, estimated_full_field_size))\n        _dupe_values = []\n        for _, _dupe_row in portfolio_df.iterrows():\n            _dupe_captain = str(_dupe_row.get("Captain", ""))\n            _dupe_flex = [str(_dupe_row.get(f"Flex{i}", "")) for i in range(1, 6)]\n            _dupe_cp = max(float(_dupe_own.get(_dupe_captain, 0.05)) * 0.20, 0.0001)\n            _dupe_fp = [max(float(_dupe_own.get(_p, 0.05)), 0.0001) for _p in _dupe_flex]\n            _dupe_raw = _dupe_cp * float(np.prod(_dupe_fp))\n            _dupe_expected = _dupe_field_size * (max(_dupe_raw, 1e-12) ** 0.62)\n            _dupe_salary = float(pd.to_numeric(pd.Series([_dupe_row.get("Salary", 50000)]), errors="coerce").fillna(50000).iloc[0])\n            _dupe_expected *= float(np.exp(-max(0.0, 50000.0 - _dupe_salary) / 9000.0))\n            _dupe_values.append(max(0, int(round(_dupe_expected)) - 1))\n        portfolio_df["Projected Dupes"] = _dupe_values\n\n    st.session_state["portfolio_df"] = portfolio_df\n    portfolio_export_df = portfolio_df[\n'''
if "_dupe_values = []" not in text:
    if anchor not in text:
        raise SystemExit("portfolio export dataframe anchor not found")
    text = text.replace(anchor, injection, 1)

for required in ('"Projected Dupes"', '_dupe_values = []', 'portfolio_export_df = portfolio_df['):
    if required not in text:
        raise SystemExit(f"Projected Dupes export marker missing: {required}")

APP.write_text(text, encoding="utf-8")
