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

start_marker = "        showdown_base_scores = np.asarray(["
end_marker = "    st.session_state[\"candidates_ready\"] = True"
start = text.find(start_marker)
if start < 0:
    raise SystemExit("legacy DK Showdown candidate block start not found")
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("legacy DK Showdown candidate block end not found")
end += len(end_marker)

replacement = '''        showdown_base_scores = np.asarray([
            player_sim[p]["P95"] * P95_WEIGHT
            + player_sim[p]["P99"] * P99_WEIGHT
            + player_sim[p]["Mean"] * MEAN_WEIGHT
            + player_sim[p].get("StdDev", 0.0) * STDDEV_WEIGHT
            for p in available_players
        ], dtype=float)
        _, showdown_ownership_proxy = ownership_adjusted_player_scores(
            players_df[players_df["Name"].isin(available_players)].drop_duplicates("Name"),
            available_players, showdown_base_scores, player_sim
        )
        showdown_ownership_by_name = {
            name: float(showdown_ownership_proxy[i])
            for i, name in enumerate(available_players)
        }
        showdown_pool = players_df[players_df["Name"].isin(available_players)].copy()
        showdown_controls = edited_controls[edited_controls["Name"].isin(available_players)].copy()
        CANDIDATE_COUNT = 5000
        candidate_progress = st.progress(0, text="Exhaustively screening legal Showdown lineups...")
        candidates_df = dk_build_showdown_candidates(
            showdown_pool,
            player_sim,
            showdown_ownership_by_name,
            controls=showdown_controls,
            candidate_count=CANDIDATE_COUNT,
            salary_floor=int(MIN_LINEUP_SALARY),
            salary_cap=int(min(SALARY_CAP, MAX_LINEUP_SALARY)),
            p95_weight=P95_WEIGHT,
            p99_weight=P99_WEIGHT,
            mean_weight=MEAN_WEIGHT,
            stddev_weight=STDDEV_WEIGHT,
        )
        st.session_state["dk_exhaustive_build_stats"] = {
            "method": "Exhaustive",
            "examined": int(candidates_df.attrs.get("examined_lineups", 0)),
            "legal": int(candidates_df.attrs.get("legal_lineups", 0)),
            "retained": int(candidates_df.attrs.get("retained_lineups", len(candidates_df))),
        }
        candidate_progress.progress(
            1.0,
            text=(
                f"Exhaustive candidate search complete: {len(candidates_df):,} retained "
                f"from {st.session_state['dk_exhaustive_build_stats']['legal']:,} legal lineups"
            ),
        )
        build_stats = st.session_state["dk_exhaustive_build_stats"]
        st.success(
            f"Build Method: EXHAUSTIVE | Examined: {build_stats['examined']:,} | "
            f"Legal: {build_stats['legal']:,} | Candidates retained: {build_stats['retained']:,}"
        )
    except Exception as exc:
        workflow_status.error(
            f"Step 2 failed while ranking players or building candidate lineups: {type(exc).__name__}: {exc}"
        )
        st.exception(exc)
        st.stop()

    st.session_state["candidates_df"] = candidates_df
    st.session_state["candidates_ready"] = True'''

text = text[:start] + replacement + text[end:]
APP.write_text(text, encoding="utf-8")
