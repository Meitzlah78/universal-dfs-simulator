"""Replace the legacy randomized DK Showdown candidate builder with the tested exhaustive adapter.

This is intentionally a deterministic source transform so the large Streamlit app can be
changed and regression-tested without hand-editing a several-thousand-line block.
"""
from __future__ import annotations

from pathlib import Path

APP = Path("dfs_app.py")
IMPORT_ANCHOR = "from dk_showdown_engine import ("
BUILD_START = "    if build_clicked:\n        showdown_base_scores = {"
BUILD_END = "        st.session_state[\"candidates_ready\"] = True"


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    import_line = "from dk_showdown_build import build_showdown_candidates as dk_build_showdown_candidates\n"
    if import_line not in text:
        pos = text.index(IMPORT_ANCHOR)
        text = text[:pos] + import_line + text[pos:]

    start = text.index(BUILD_START)
    end = text.index(BUILD_END, start) + len(BUILD_END)
    replacement = '''    if build_clicked:
        showdown_base_scores = {
            name: float(player_sim.get(name, {}).get("Mean", 0.0))
            for name in available_players
        }
        _, showdown_ownership_proxy = ownership_adjusted_player_scores(
            showdown_base_scores,
            players_df[players_df["Name"].isin(available_players)],
            player_sim,
        )
        build_pool = players_df[players_df["Name"].isin(available_players)][["Name", "Salary", "Team"]].copy()
        candidates_df = dk_build_showdown_candidates(
            build_pool,
            player_sim,
            showdown_ownership_proxy,
            controls=edited_controls,
            candidate_count=5000,
            salary_floor=0,
            salary_cap=50000,
        )
        if candidates_df.empty:
            st.error("No legal Showdown candidates matched the current hard build constraints.")
            st.stop()
        st.session_state["candidates_df"] = candidates_df
        st.session_state["candidates_ready"] = True
        st.session_state["showdown_build_diagnostics"] = {
            "examined": int(candidates_df.attrs.get("examined_lineups", 0)),
            "legal": int(candidates_df.attrs.get("legal_lineups", 0)),
            "retained": int(candidates_df.attrs.get("retained_lineups", len(candidates_df))),
        }'''
    text = text[:start] + replacement + text[end:]
    APP.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
