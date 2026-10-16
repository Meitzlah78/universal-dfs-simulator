"""Expose Projected Dupes in DK Showdown result tables and CSV exports."""
from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

anchor = 'def add_field_ranking_metrics(frame, field_scores, score_column="ProjectedPoints"):\n'
helper = '''def add_dk_projected_dupes(frame, player_pool=None, contest_size=None):\n    """Attach expected competing copies without changing lineup selection rules."""\n    if frame is None or frame.empty or "Captain" not in frame.columns:\n        return frame\n    result = frame.copy()\n    flex_cols = [f"Flex{i}" for i in range(1, 6)]\n    if not all(c in result.columns for c in flex_cols):\n        return result\n    size = int(contest_size or st.session_state.get("contest_field_size", 0) or MAX_SIMULATED_OPPONENTS)\n    pool = player_pool if isinstance(player_pool, pd.DataFrame) else pd.DataFrame()\n    own, cpt_own = {}, {}\n    if not pool.empty and "Name" in pool.columns:\n        lookup = {str(c).strip().casefold(): c for c in pool.columns}\n        own_col = next((lookup[k] for k in ("field own %", "projected own %", "ownership %", "projected ownership", "ownership", "own%", "own") if k in lookup), None)\n        cpt_col = next((lookup[k] for k in ("field cpt own %", "captain/mvp ownership %", "captain ownership %", "captain exp %") if k in lookup), None)\n        for _, prow in pool.iterrows():\n            name = str(prow.get("Name", "")).strip()\n            if not name:\n                continue\n            if own_col:\n                own[name] = max(float(pd.to_numeric(pd.Series([prow.get(own_col)]), errors="coerce").fillna(0).iloc[0]), 0.01) / 100.0\n            if cpt_col:\n                cpt_own[name] = max(float(pd.to_numeric(pd.Series([prow.get(cpt_col)]), errors="coerce").fillna(0).iloc[0]), 0.01) / 100.0\n    estimates = []\n    for _, row in result.iterrows():\n        captain = str(row["Captain"]); flex = [str(row[c]) for c in flex_cols]\n        cp = cpt_own.get(captain, own.get(captain, 0.05) * 0.20)\n        raw = cp * float(np.prod([own.get(p, 0.05) for p in flex]))\n        expected = size * (max(raw, 1e-12) ** 0.62)\n        salary = float(pd.to_numeric(pd.Series([row.get("Salary", 50000)]), errors="coerce").fillna(50000).iloc[0])\n        expected *= float(np.exp(-max(0.0, 50000.0 - salary) / 9000.0))\n        estimates.append(max(0, int(round(expected)) - 1))\n    result["Projected Dupes"] = estimates\n    return result\n\n\n'''
if "def add_dk_projected_dupes(" not in text:
    if anchor not in text:
        raise SystemExit("ranking helper anchor not found")
    text = text.replace(anchor, helper + anchor, 1)

# Patch CSV expressions conservatively: only simple DataFrame variable exports.
# The transformed app uses final_lineups for the user portfolio export.
for var in ("final_lineups", "display_lineups", "portfolio_df"):
    old = f'{var}.to_csv(index=False)'
    new = f'{var}.pipe(add_dk_projected_dupes, player_pool=locals().get("player_pool", locals().get("pool", None)), contest_size=st.session_state.get("contest_field_size", None)).to_csv(index=False)'
    text = text.replace(old, new)

APP.write_text(text, encoding="utf-8")
