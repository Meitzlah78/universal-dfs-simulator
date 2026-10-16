"""Install the tested exhaustive DK Showdown candidate builder into dfs_app.py.

This source transform is intentionally deterministic and fails closed if the
expected legacy block is not found. It keeps diversification out of BUILD:
5,000 competitive candidates are built first, Contest Sim scores them later,
and portfolio diversification remains a post-sim concern.
"""
from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

import_anchor = "from dk_showdown_engine import (\n"
new_import = "from dk_showdown_build import build_showdown_candidates as dk_build_showdown_candidates\n"
if new_import not in text:
    if import_anchor not in text:
        raise SystemExit("DK engine import anchor not found")
    text = text.replace(import_anchor, new_import + import_anchor, 1)

start_marker = "    showdown_base_scores = {"
end_marker = "    st.session_state[\"candidates_ready\"] = True"
start = text.find(start_marker)
if start < 0:
    raise SystemExit("legacy DK Showdown candidate block start not found")
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("legacy DK Showdown candidate block end not found")
end += len(end_marker)

replacement = '''    showdown_base_scores = {
        name: float(player_sim[name].get("P95", 0.0))
        for name in available_players
        if name in player_sim
    }
    _, showdown_ownership_proxy = ownership_adjusted_player_scores(
        showdown_base_scores,
        players_df,
        control_map,
        available_players,
        upside_scores={name: float(player_sim[name].get("P99", 0.0)) for name in available_players if name in player_sim},
    )
    showdown_pool = players_df[players_df["Name"].isin(available_players)].copy()
    showdown_controls = edited_controls[edited_controls["Name"].isin(available_players)].copy()
    CANDIDATE_COUNT = 5000
    candidates_df = dk_build_showdown_candidates(
        showdown_pool,
        player_sim,
        showdown_ownership_proxy,
        controls=showdown_controls,
        candidate_count=CANDIDATE_COUNT,
        salary_floor=0,
        salary_cap=50000,
    )
    st.session_state["dk_exhaustive_build_stats"] = {
        "examined": int(candidates_df.attrs.get("examined_lineups", 0)),
        "legal": int(candidates_df.attrs.get("legal_lineups", 0)),
        "retained": int(candidates_df.attrs.get("retained_lineups", len(candidates_df))),
    }
    st.session_state["candidates_df"] = candidates_df
    st.session_state["candidates_ready"] = True'''

text = text[:start] + replacement + text[end:]
APP.write_text(text, encoding="utf-8")
