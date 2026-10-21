import itertools
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import requests
import streamlit as st
import pandas as pd
import numpy as np
from zoneinfo import ZoneInfo

# Lower defaults keep the simulator responsive while retaining useful variation.
SIMULATION_COUNT = 10000
MAX_SIMULATED_OPPONENTS = 10000

st.set_page_config(
    page_title="Simmah | NFL DFS Simulator",
    page_icon="🏈",
    layout="wide"
)

from simmah_slate_workspaces import begin_workspaces, finish_workspaces, select_upload, workspace_file_uploader, workspace_stop, workspace_rerun
_loaded_slate_tabs = begin_workspaces(st)
from simmah_injury_display import injury_frame, injury_player_pool
from simmah_single_stacks import render_controls as render_single_stack_controls, selected_validator as single_stack_validator
from simmah_build_state import uploaded_slate_signature, signature_matches_upload
from simmah_lineup_editor import render_editor
from simmah_ui import render_brand, player_columns, player_column_config, render_diversity_controls
render_brand(st)
st.session_state["active_game_markets"] = {}
st.session_state["active_game_lines"] = []
st.session_state["active_slate_identity"] = ""

# Shared header stays above the three format-independent workspaces.
_shared_header = st.container()
_slate_games_header = st.container(key="simmah_pinned_games")
_workspace_main, _workspace_rail = st.columns([4.3, 1.25], gap="medium")
with _workspace_main:
    _tab_contests, _tab_roster, _tab_build, _tab_lineups = st.tabs(["Contests", "Roster & Projections", "Build", "Lineups"])
with _workspace_rail:
    _build_controls = st.container(key="simmah_build_panel", border=True)
    with _build_controls:
        st.markdown("### Build Lineups")
        st.caption("10,000 player simulations · 5,000 candidate target")

with _tab_contests:
    st.caption("1. Upload your entries file, select a contest, and confirm its field size and payouts.")
    _contest_setup = st.container()
    _contest_history = st.container()
with _tab_roster:
    st.caption("2. Review projections, injuries, weather and player controls for the selected slate.")
with _tab_build:
    st.caption("3. Build, rank and select your portfolio, then export it into your existing entries.")

@st.cache_data(show_spinner=False, max_entries=8)
def leverage_opportunities_cached(outcomes, candidates):
    from simmah_leverage import candidate_opportunities
    return candidate_opportunities(outcomes, candidates)


def render_portfolio_roi_panel(portfolio, contest=None):
    from simmah_portfolio import portfolio_roi_totals
    totals = portfolio_roi_totals(portfolio, contest)
    st.write("### Portfolio ROI")
    columns = st.columns(5)
    columns[0].metric("Assigned entries", f"{totals['entries']:,}")
    for column, key, label in zip(columns[1:], ("fees","winnings","net","roi"),
                                  ("Entry fees","Estimated winnings","Estimated net profit","Estimated ROI")):
        value = totals[key]
        display = "Pending" if value is None else (f"{value:,.1f}%" if key == "roi" else f"${value:,.2f}")
        column.metric(label, display)
    if totals["roi"] is None:
        st.caption("Run the contest simulation with a confirmed field size, entry fee and payout schedule for ROI estimates.")
    else:
        st.caption("Simulation estimate for the assigned portfolio. The opponent field and expected returns remain unvalidated.")


def render_entry_export_header(site):
    """Keep the entry-upload controls consistent across every roster format."""
    st.write("### Export")
    st.caption("Download the file for your existing entries, then open the site and upload it through Edit Entries. Entry IDs and contest details are preserved.")
    label, url = (
        ("OPEN FANDUEL / EDIT ENTRIES", "https://www.fanduel.com/upcoming")
        if site == "FanDuel"
        else ("OPEN DRAFTKINGS MY LINEUPS / EDIT ENTRIES", "https://www.draftkings.com/lineup")
    )
    st.link_button(label, url, use_container_width=True)


from pathlib import Path
from simmah_contest_history import (
    load_store, save_store, update_store, merge_stores, ingest_frames, read_standings,
    matching_profiles, calibrate_field, name_key,
)
_HISTORY_ROOT = Path(__file__).resolve().parent / "data"
_HISTORY_LOCAL = _HISTORY_ROOT / "field_history_local.json"
try:
    _history_store = merge_stores(load_store(_HISTORY_ROOT / "field_history_seed.json"), load_store(_HISTORY_LOCAL))
except Exception as _history_error:
    _history_store = load_store(_HISTORY_ROOT / "field_history_seed.json")
    st.warning("Saved field-history backup could not load; using checked-in profiles only.")
st.session_state["field_history_store"] = _history_store

with _contest_history:
    with st.expander("Contest History / Field Learning", expanded=False):
        st.caption("Completed standings train anonymous construction profiles used by matching opponent fields. Import all entries, not just winning lineups.")
        _hist_files = workspace_file_uploader(st,"Completed contest standings (CSV or ZIP)", type=["csv", "zip"], accept_multiple_files=True, key="contest_history_uploads_v2")
        _hc1, _hc2, _hc3 = st.columns(3)
        _hist_platform = _hc1.selectbox("Platform", ["Auto", "DraftKings", "FanDuel"], key="history_platform_v2")
        _hist_mode = _hc2.selectbox("Mode", ["Auto", "Classic / Full Roster", "Showdown / Single Game"], key="history_mode_v2")
        _hist_fee_known = _hc3.checkbox("Entry fee is known", value=False)
        _hist_fee = _hc3.number_input("Historical entry fee ($)", min_value=0., value=.10, step=.10) if _hist_fee_known else None
        _hist_max = st.number_input("Historical max entries per user (0 = unknown)", min_value=0, value=0, step=1)
        _hist_slate_date = st.date_input("Historical slate date for player-score archive (optional)", value=None, key="history_outcome_slate_date")
        _hist_metadata_file = workspace_file_uploader(st,"Optional player metadata from THAT contest (Name, Team, Position, Salary, Opponent)", type=["csv"], key="history_metadata_v2")
        st.caption("Without historical player metadata, only ownership-concentration features can be learned. Today's salaries/teams are never substituted.")
        if _hist_files and st.button("LEARN FROM CONTESTS", key="learn_contest_history_v2", use_container_width=True):
            import hashlib
            _metadata = None
            if _hist_metadata_file is not None:
                try:
                    _metadata_frame = pd.read_csv(_hist_metadata_file)
                    if "Name" not in _metadata_frame:
                        raise ValueError("Historical metadata needs a Name column")
                    if _metadata_frame["Name"].duplicated().any():
                        raise ValueError("Use one row per player with base salary, not separate CPT/MVP rows")
                    if "Salary" in _metadata_frame:
                        _metadata_frame["Salary"] = pd.to_numeric(_metadata_frame["Salary"].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
                    _metadata = {name_key(row["Name"]): row for row in _metadata_frame.to_dict("records")}
                except Exception as _exc:
                    st.error(f"Historical metadata could not load: {_exc}")
                    workspace_stop(st, _loaded_slate_tabs)
            _new_profiles = []
            _known = {profile["id"]: profile for profile in _history_store["contests"]}
            for _file in _hist_files:
                try:
                    _raw = _file.getvalue()
                    _standings_frames = read_standings(_raw, _file.name)
                    _profiles = ingest_frames(_standings_frames, hashlib.sha256(_raw).hexdigest(),
                        platform=_hist_platform, mode=_hist_mode, fee=_hist_fee, max_entries=int(_hist_max) or None, metadata=_metadata)
                    from simmah_nfl_outcomes import archive_completed_scores
                    try:
                        _outcome_saved = archive_completed_scores(st.session_state,_standings_frames,_profiles,
                            hashlib.sha256(_raw).hexdigest(),_file.name,
                            _hist_slate_date.isoformat() if _hist_slate_date else None)
                        if _outcome_saved['player_scores_added']:
                            st.caption(f"Saved {_outcome_saved['player_scores_added']} explicit published player scores separately for validation.")
                    except ValueError as _outcome_error:
                        st.warning("Player-score archive skipped: "+str(_outcome_error))
                    _new_profiles.extend(profile for profile in _profiles if profile["id"] not in _known or
                        set(profile["features"]) > set(_known[profile["id"]]["features"]) or
                        (_known[profile["id"]].get("stake_bucket")=="UNKNOWN" and profile.get("stake_bucket")!="UNKNOWN") or
                        (_known[profile["id"]].get("max_entries") is None and profile.get("max_entries") is not None))
                except Exception as _exc:
                    st.warning(f"{_file.name}: {_exc}")
            if _new_profiles:
                _history_store = merge_stores(_history_store, {"schema": 1, "contests": _new_profiles})
                _history_store = update_store(_HISTORY_LOCAL, _history_store)
                st.session_state["field_history_store"] = _history_store
                st.success(f"Learned {len(_new_profiles)} contest profile(s), covering {sum(p['lineups'] for p in _new_profiles):,} complete entries.")
            else:
                st.info("No new valid contest profiles were added.")
        import json as _history_json
        _restore = workspace_file_uploader(st,"Restore a Simmah field-history backup", type=["json"], key="history_restore_v2")
        if _restore is not None and st.button("RESTORE FIELD HISTORY"):
            try:
                _history_store = merge_stores(_history_store, _history_json.loads(_restore.getvalue()))
                _history_store = update_store(_HISTORY_LOCAL, _history_store)
                st.session_state["field_history_store"] = _history_store
                st.success("Field-history profiles restored; identical imports were deduplicated.")
            except Exception as _exc:
                st.error(f"Backup could not be restored: {_exc}")
        st.caption(f"Available: {len(_history_store['contests'])} contest profile(s), {sum(p['lineups'] for p in _history_store['contests']):,} historical entries.")
        if _history_store["contests"]:
            st.dataframe(injury_frame(st, pd.DataFrame([{"Format": p["format"], "Stakes": p["stake_bucket"], "Entries": p["lineups"], "Learned features": ", ".join(p["features"])} for p in _history_store["contests"]])), use_container_width=True, hide_index=True)
        st.download_button("DOWNLOAD FIELD-HISTORY BACKUP", _history_json.dumps(_history_store, indent=2), "Simmah_Field_History.json", "application/json")
        st.caption("New profiles survive app reruns and sessions on this server. Download a backup to retain them across hosting redeploys; checked-in seed profiles are always restored.")
        from simmah_nfl_outcomes import load_seed_results
        try:
            load_seed_results(st.session_state,_HISTORY_ROOT / "nfl_results")
        except (OSError,ValueError,KeyError,TypeError) as _outcome_seed_error:
            st.warning("Saved player-result seed could not load: "+str(_outcome_seed_error))
        _completed_scores = st.session_state.get("nfl_completed_player_results",{})
        if _completed_scores:
            from simmah_slate_workspaces import workspace_download_button
            st.caption(f"{len(_completed_scores)} published player-score snapshots saved in this slate workspace. Scores are retained for validation; saving them does not automatically tune projections. Missing scores remain unknown.")
            workspace_download_button(st,"EXPORT NFL COMPLETED PLAYER RESULTS",
                _history_json.dumps({"schema":1,"snapshots":_completed_scores},indent=2,allow_nan=False).encode(),
                "Simmah_NFL_Completed_Player_Results.json","application/json",
                key="nfl_completed_results_export",on_click="ignore")



from datetime import datetime as _sticky_datetime

# Keep the refresh control in the sticky top bar, without the projection-update warning.
with _shared_header.container(key="sticky_projection_bar"):
    _sticky_left, _sticky_right = st.columns([3, 2])
    with _sticky_left:
        st.markdown("**Uploaded CSVs still take priority.**")
    with _sticky_right:
        if st.button("REFRESH PROJECTIONS + INJURY NEWS", key="sticky_refresh_projections", use_container_width=True):
            # Defer cache clearing until after the cached functions have been defined.
            st.session_state["refresh_projections_requested"] = True
            workspace_rerun(st, _loaded_slate_tabs)


# Shared ranking choices across every supported format.
PORTFOLIO_METRICS = {
    "Contest Score": "ContestScore",
    "Win %": "WinRate",
    "Top 1%": "Top1",
    "Top 5%": "Top5",
    "Top 10%": "Top10",
    "Cash %": "CashRate",
    "Average Percentile": "AvgPercentile",
}


def add_field_ranking_metrics(frame, field_scores, score_column="ProjectedPoints"):
    """Add comparable field-based ranking columns for formats without full outcome scoring."""
    ranked = frame.copy()
    scores = pd.to_numeric(ranked.get(score_column, pd.Series(index=ranked.index, dtype=float)), errors="coerce").fillna(0).to_numpy(dtype=float)
    field = np.asarray(field_scores, dtype=float)
    if not len(field):
        field = scores.copy()
    if not len(field):
        field = np.array([0.0])
    percentiles = np.asarray([np.mean(field <= score) for score in scores], dtype=float)
    win_rates = np.asarray([float(np.mean(field < score) >= 1.0) for score in scores], dtype=float)
    ranked["WinRate"] = win_rates
    ranked["Top1"] = (percentiles >= 0.99).astype(float)
    ranked["Top5"] = (percentiles >= 0.95).astype(float)
    ranked["Top10"] = (percentiles >= 0.90).astype(float)
    ranked["CashRate"] = (percentiles >= 0.50).astype(float)
    ranked["AvgPercentile"] = percentiles
    ranked["ContestScore"] = (
        ranked["Top1"] * 0.40 + ranked["Top5"] * 0.25
        + ranked["Top10"] * 0.20 + ranked["CashRate"] * 0.10
        + ranked["WinRate"] * 0.05
    )
    return ranked


# Quick link to DraftKings lineup upload.
with _contest_setup:
    with st.expander("DraftKings entry / salary links", expanded=False):
        top_buttons = st.columns(2)
        with top_buttons[0]:
            st.link_button(
                "EDIT ENTRIES",
                "https://www.draftkings.com/entry/upload",
                use_container_width=True,
            )
        with top_buttons[1]:
            st.link_button(
                "SALARY",
                "https://www.draftkings.com/lineup/upload",
                use_container_width=True,
            )


def is_full_game_contest_name(value):
    """Reject partial-game/live contests but allow both full-game and single-game formats."""
    name = str(value or "").strip().lower()
    partial_patterns = [
        r"\b(?:1st|2nd|3rd|4th|first|second|third|fourth)\s*(?:quarter|qtr|half)\b",
        r"\b(?:first half|second half|1st half|2nd half|quarter contest|half contest)\b",
        r"\b(?:live|in[- ]?game)\b",
    ]
    return not any(re.search(pattern, name, flags=re.IGNORECASE) for pattern in partial_patterns)


def is_single_game_contest_name(value):
    """Identify single-game formats without excluding them from full-game contests."""
    name = str(value or "").strip().lower()
    return bool(re.search(r"\b(showdown|single game|single-game|mvp|captain)\b", name))


def remove_duplicate_entries(frame, entry_id_col=None):
    """Count each uploaded contest entry once when an entry identifier is available."""
    if frame is None or frame.empty:
        return frame
    if entry_id_col and entry_id_col in frame.columns:
        clean = frame.copy()
        clean[entry_id_col] = clean[entry_id_col].astype(str).str.strip()
        clean = clean.drop_duplicates(subset=[entry_id_col], keep="first")
        return clean
    return frame.drop_duplicates(keep="first")


FULL_ROSTER_STACK_OPTIONS = [
    "Single stack: QB + 1 WR/TE",
    "Double stack: QB + 2 WR/TE",
    "Single stack + bring-back",
    "Double stack + bring-back",
]
ANY_STACK_OPTION = "Any / All stacks (includes no stack)"
NO_STACK_OPTION = "No stack: no QB + WR/TE"
BUILD_STACK_OPTIONS = [ANY_STACK_OPTION, *FULL_ROSTER_STACK_OPTIONS, NO_STACK_OPTION]
SECONDARY_STACK_OPTIONS = ["RB + same-team defense", "Secondary game mini-stack"]


def full_roster_stack_patterns(selected_stacks):
    """Any (or no selection) leaves construction unrestricted, including no stack."""
    if not selected_stacks or ANY_STACK_OPTION in selected_stacks:
        return None
    patterns = dict(zip(FULL_ROSTER_STACK_OPTIONS, [(1, False), (2, False), (1, True), (2, True)]))
    patterns[NO_STACK_OPTION] = (0, False)
    return [patterns[label] for label in selected_stacks if label in patterns]


def full_roster_stack_lookup(pool):
    """Build once per candidate run, rather than indexing pandas for every roster."""
    return pool.drop_duplicates("Name", keep="first").set_index("Name").to_dict("index")


def full_roster_stack_matches(chosen, pool, selected_stacks, stack_lookup=None, secondary_stacks=None):
    """Match any selected primary structure and every selected secondary rule."""
    if not isinstance(chosen, dict):
        return False
    lookup = stack_lookup if stack_lookup is not None else full_roster_stack_lookup(pool)
    if isinstance(lookup, pd.DataFrame):
        lookup = lookup.to_dict("index")
    qb_name = str(chosen.get("QB", "")).strip()
    qb = lookup.get(qb_name, {})
    qb_team = str(qb.get("Team", "")).strip().upper()
    qb_opp = str(qb.get("Opponent", "")).strip().upper()
    if not qb_team:
        return False
    players = []
    for slot, name in chosen.items():
        if slot == "QB":
            continue
        row = lookup.get(str(name).strip(), {})
        pos = str(row.get("Position", "")).upper().replace(" ", "").split("/")[0]
        team = str(row.get("Team", "")).strip().upper()
        opp = str(row.get("Opponent", "")).strip().upper()
        players.append((pos, team, opp))
    pass_catchers = sum(pos in {"WR", "TE"} and team == qb_team for pos, team, _ in players)
    bring_back = any(pos in {"RB", "WR", "TE"} and team == qb_opp for pos, team, _ in players) if qb_opp else False
    rules = {
        ANY_STACK_OPTION: True,
        NO_STACK_OPTION: pass_catchers == 0,
        FULL_ROSTER_STACK_OPTIONS[0]: pass_catchers == 1,
        FULL_ROSTER_STACK_OPTIONS[1]: pass_catchers == 2,
        FULL_ROSTER_STACK_OPTIONS[2]: pass_catchers == 1 and bring_back,
        FULL_ROSTER_STACK_OPTIONS[3]: pass_catchers == 2 and bring_back,
    }
    if selected_stacks and not any(rules.get(rule, False) for rule in selected_stacks):
        return False
    secondary = set(secondary_stacks or [])
    if SECONDARY_STACK_OPTIONS[0] in secondary:
        defense_teams = {team for pos, team, _ in players if pos in {"D", "DST", "DEF"} and team}
        if not any(pos == "RB" and team in defense_teams for pos, team, _ in players):
            return False
    if SECONDARY_STACK_OPTIONS[1] in secondary:
        # Two opposing skill players from a game outside the primary QB game.
        skills = [(team, opp) for pos, team, opp in players
                  if pos in {"RB", "WR", "TE"} and team and opp and team not in {qb_team, qb_opp}]
        if not any(team_a == opp_b and team_b == opp_a
                   for i, (team_a, opp_a) in enumerate(skills)
                   for team_b, opp_b in skills[i + 1:]):
            return False
    return True


def preserve_uploaded_ownership(players, raw):
    """Keep pregame ownership inputs; never reuse simulated field ownership."""
    aliases = {
        "Projected Ownership": ("projected own %", "ownership %", "projected ownership", "projected own", "ownership", "own%", "own"),
        "Projected MVP Ownership": ("projected mvp ownership", "mvp ownership %", "mvp own %"),
        "Projected Flex Ownership": ("projected flex ownership", "flex ownership %", "flex own %"),
    }
    lookup = {str(c).strip().casefold():c for c in raw.columns}
    result = players.copy()
    for target, names in aliases.items():
        source = next((lookup[name] for name in names if name in lookup), None)
        if source is not None:
            values = pd.to_numeric(raw[source].astype(str).str.strip().str.replace("%", "", regex=False), errors="coerce")
            result[target] = values.where(np.isfinite(values) & values.between(0,100))
    return result


@st.cache_data(ttl=900, show_spinner=False)
def fetch_footballguys_ownership(site):
    from simmah_footballguys import URL
    response = requests.get(URL, params={"site": site}, timeout=12)
    response.raise_for_status()
    return response.text


def attach_main_slate_ownership(pool, site):
    from simmah_footballguys import apply_footballguys, has_uploaded_ownership
    if has_uploaded_ownership(pool):
        st.caption("Uploaded ownership retained; automatic ownership skipped.")
        return pool
    try:
        pool, note = apply_footballguys(pool, fetch_footballguys_ownership(site), site)
        st.caption(note)
    except Exception as exc:
        st.caption(f"Footballguys ownership unavailable: {exc}. Using estimated popularity.")
    return pool


def opponent_field_selection_weights(pool, fallback_scores):
    """Use ownership as the primary opponent-construction signal for full-roster contests."""
    from simmah_game_lines import field_market_factors
    context = globals().get("st")
    markets = getattr(context, "session_state", {}).get("active_game_markets", {})
    market_factors = field_market_factors(pool, markets)
    fallback = np.asarray(fallback_scores, dtype=float)
    lookup = {str(c).strip().casefold(): c for c in pool.columns}
    # Never feed ownership measured from a previous simulated field back into
    # the next FanDuel opponent build. That creates a self-reinforcing field and
    # can make the representative opponents much weaker than the user's lineups.
    # Prefer true/pregame projected ownership; fall back to projection/value
    # proxy below when no external ownership is available.
    own_col = next((lookup[k] for k in (
        "ownership selection weight", "projected own %", "ownership %", "projected ownership",
        "projected own", "ownership", "own%", "own"
    ) if k in lookup), None)
    if own_col is not None:
        ownership = pd.to_numeric(pool[own_col].astype(str).str.strip().str.replace("%", "", regex=False), errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float)
        ownership = np.clip(ownership, 0.0, None)
        if ownership.sum() > 0:
            # The combined selection column can include explicitly marked fallback rows.
            if "Ownership Source" in pool:
                estimated = pool["Ownership Source"].astype(str).str.contains("fallback", case=False).to_numpy()
                ownership[estimated] *= market_factors[estimated]
            return np.clip(ownership, 0.01, None)

    # Before field ownership exists, use projection/value estimates rather than
    # forcing the user's stack rules onto opponents.
    if not len(fallback):
        return fallback
    from simmah_field_popularity import estimated_field_weights
    return estimated_field_weights(pool, fallback) * market_factors


def render_value_leverage_finder(pool, comparison, field, slots, key, special_slot=None):
    from simmah_leverage import leverage_report
    report = leverage_report(pool, comparison, field, slots, special_slot)
    with st.expander("Value & leverage finder", expanded=True):
        st.caption("Value = projected points per $1,000; position percentile compares players at the same position. Leverage = Top-1%-weighted candidate presence minus simulated field ownership. This is a candidate-dependent signal, not optimal-lineup probability or a guaranteed edge.")
        if report["Sim Leverage (pp)"].notna().any():
            st.caption(f"Based on {report.attrs.get('evaluated_unique_candidates', 0):,} distinct evaluated candidates with positive Top-1% rates and {report.attrs.get('field_entries', 0):,} simulated field entries. Candidate limits, locks and stacks influence these results.")
        else:
            st.caption("Value is available now. Leverage needs a completed contest comparison and opponent field; missing estimates stay blank.")
        options = ["Projected Pts / $1k", "Position Value Percentile", "Sim Leverage (pp)"]
        options = [c for c in options if c in report]
        sort = st.selectbox("Find plays by", options, index=options.index("Sim Leverage (pp)") if report["Sim Leverage (pp)"].notna().any() else 0, key="leverage_sort_" + key)
        cols = [c for c in ["Name", "Team", "Position", "Salary", "Projection", "Projected Pts / $1k", "P95 Pts / $1k", "Position Value Percentile", "Top1-weighted Presence %", "Field Own %", "Sim Leverage (pp)", "CPT/MVP Weighted Presence %", "Field CPT/MVP Own %", "CPT/MVP Leverage (pp)"] if c in report]
        st.dataframe(injury_frame(st, report[cols].sort_values(sort, ascending=False, na_position="last")), hide_index=True, use_container_width=True)


def ownership_adjusted_player_scores(pool, names, base_scores, player_sim, projection_fallback=None):
    """Subtract an ownership tax, while allowing strong simulated upside to offset it."""
    names = list(names)
    base_scores = np.asarray(base_scores, dtype=float)
    lookup = {str(c).strip().lower(): c for c in pool.columns}
    ownership_col = next(
        (lookup[k] for k in ("projected ownership", "ownership", "own%", "ownership %", "projected own", "own")
         if k in lookup),
        None
    )
    name_col = lookup.get("name")
    actual_ownership = {}
    if ownership_col is not None and name_col is not None:
        for _, row in pool[[name_col, ownership_col]].dropna(subset=[name_col]).iterrows():
            try:
                value = float(str(row[ownership_col]).replace("%", "").strip())
                if value > 0:
                    actual_ownership[str(row[name_col])] = value
            except (TypeError, ValueError):
                pass

    # If the uploaded data has no ownership, use a clearly labeled internal proxy:
    # players with stronger baseline scores are treated as more likely to be popular.
    if actual_ownership:
        ownership = np.asarray([actual_ownership.get(str(n), np.nan) for n in names], dtype=float)
        missing = ~np.isfinite(ownership)
        if missing.any():
            ranks = pd.Series(base_scores).rank(pct=True).to_numpy()
            ownership[missing] = 5.0 + 30.0 * ranks[missing]
    else:
        ranks = pd.Series(base_scores).rank(pct=True).to_numpy()
        ownership = 5.0 + 30.0 * ranks

    ownership = np.clip(ownership, 0.0, 100.0)
    upside = np.asarray([
        max(
            0.0,
            float(player_sim.get(str(name), {}).get("P99", base_scores[i]))
            - float(player_sim.get(str(name), {}).get("P95", base_scores[i]))
        )
        for i, name in enumerate(names)
    ], dtype=float)

    # Only tax ownership above 15%. Big P99-vs-P95 upside reduces the tax.
    raw_tax = np.maximum(ownership - 15.0, 0.0) * 0.06
    upside_credit = np.minimum(raw_tax, upside * 0.08)
    adjusted = np.maximum(0.01, base_scores - raw_tax + upside_credit)
    return adjusted, ownership


def calculate_field_ownership(field_df, slots, captain_slot=None):
    """Calculate unique-lineup ownership and Captain/MVP ownership separately."""
    columns = ["Name", "Ownership %", "Captain/MVP Ownership %"]
    if field_df is None or field_df.empty:
        return pd.DataFrame(columns=columns)
    valid_slots = [slot for slot in slots if slot in field_df.columns]
    total_lineups = len(field_df)
    if not valid_slots or total_lineups == 0:
        return pd.DataFrame(columns=columns)

    # Overall ownership counts a player once per lineup, even if a name appears
    # in more than one slot. Captain/MVP ownership counts only that special slot.
    slot_values = field_df[valid_slots].astype("string").apply(lambda col: col.str.strip())
    invalid_names = {"", "nan", "none", "<na>"}
    lineup_counts = {}
    for row in slot_values.itertuples(index=False, name=None):
        names_in_lineup = {
            str(name).strip()
            for name in row
            if pd.notna(name) and str(name).strip().casefold() not in invalid_names
        }
        for name in names_in_lineup:
            lineup_counts[name] = lineup_counts.get(name, 0) + 1

    captain_counts = {}
    if captain_slot and captain_slot in valid_slots:
        for value in slot_values[captain_slot]:
            if pd.notna(value) and str(value).strip().casefold() not in invalid_names:
                name = str(value).strip()
                captain_counts[name] = captain_counts.get(name, 0) + 1

    # Captain/MVP ownership is a subset of overall ownership by definition.
    names = sorted(set(lineup_counts) | set(captain_counts))
    return pd.DataFrame([{
        "Name": name,
        "Ownership %": round(100 * lineup_counts.get(name, 0) / total_lineups, 2),
        "Captain/MVP Ownership %": round(
            100 * min(captain_counts.get(name, 0), lineup_counts.get(name, 0)) / total_lineups, 2
        ),
    } for name in names]).sort_values("Ownership %", ascending=False).reset_index(drop=True)


def show_field_ownership(field_df, slots, title, captain_slot=None):
    ownership_df = calculate_field_ownership(field_df, slots, captain_slot)
    st.session_state["latest_field_ownership"] = ownership_df
    current_format = str(st.session_state.get("dfs_format", "")).strip()
    if current_format:
        ownership_by_format = st.session_state.get("latest_field_ownership_by_format")
        if not isinstance(ownership_by_format, dict):
            ownership_by_format = {}
        ownership_by_format[current_format] = ownership_df.copy()
        st.session_state["latest_field_ownership_by_format"] = ownership_by_format
    if not ownership_df.empty:
        st.write("### " + title)
        st.caption(f"Ownership calculated from {len(field_df):,} simulated opponent lineups. Captain/MVP ownership is shown separately where applicable.")
        st.dataframe(
            injury_frame(st, ownership_df),
            use_container_width=True,
            hide_index=True,
            column_config={"Name": st.column_config.TextColumn("Name", pinned=True)},
        )


def add_lineup_field_ownership(portfolio_df):
    """Add a lineup ownership score based on player ownership in the simulated field."""
    ownership_df = st.session_state.get("latest_field_ownership")
    if not isinstance(ownership_df, pd.DataFrame) or ownership_df.empty or "Name" not in ownership_df.columns:
        return portfolio_df

    field_ownership = dict(zip(
        ownership_df["Name"].astype(str),
        pd.to_numeric(ownership_df["Ownership %"], errors="coerce").fillna(0.0)
    ))
    captain_series = ownership_df["Captain/MVP Ownership %"] if "Captain/MVP Ownership %" in ownership_df.columns else pd.Series(0.0, index=ownership_df.index)
    captain_ownership = dict(zip(
        ownership_df["Name"].astype(str),
        pd.to_numeric(captain_series, errors="coerce").fillna(0.0)
    ))
    # Support every roster format by detecting lineup slots from known roster names
    # and excluding common non-player/stat columns.
    known_slots = {
        "Captain", "MVP", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5",
        "QB", "RB", "RB1", "RB2", "RB3", "WR", "WR1", "WR2", "WR3", "WR4",
        "TE", "FLEX", "UTIL", "DST", "D", "DEF", "K", "P", "G", "F", "C",
        "PG", "SG", "SF", "PF", "CPT"
    }
    slots = [col for col in portfolio_df.columns if str(col).strip() in known_slots]
    if not slots:
        return portfolio_df

    result = portfolio_df.copy()
    def score_lineup(row):
        total = 0.0
        for slot in slots:
            player = str(row.get(slot, "")).strip()
            if not player or player.lower() in {"nan", "none"}:
                continue
            if slot in {"Captain", "MVP"} and captain_ownership.get(player, 0.0) > 0:
                total += captain_ownership[player]
            else:
                total += field_ownership.get(player, 0.0)
        return round(total, 2)

    result["Lineup Ownership Score (%)"] = result.apply(score_lineup, axis=1)
    return result


def learned_field_profiles(platform_name, mode_name, contest, roster_size, pool=None):
    contest = contest or {}
    fee = contest.get("entry_fee", contest.get("entry"))
    maximum = contest.get("max_entries_per_user", contest.get("max_entries"))
    game_count = None
    if isinstance(pool, pd.DataFrame) and "Team" in pool:
        teams = pool["Team"].dropna().astype(str).str.strip()
        team_count = teams[teams.ne("")].nunique()
        if team_count and team_count % 2 == 0:
            game_count = team_count // 2
    return matching_profiles(st.session_state.get("field_history_store", {"schema": 1, "contests": []}),
        platform_name, mode_name, fee=fee, max_entries=maximum, roster_size=roster_size, game_count=game_count)


def opponent_construction_distribution(platform_name, mode_name, contest, pool):
    from simmah_field_construction import learned_construction_distribution
    return learned_construction_distribution(
        learned_field_profiles(platform_name, mode_name, contest, 9, pool))


def ownership_proposal_target(pool, mode_name, target):
    from simmah_field_ownership import has_ownership_targets
    return 5 * int(target) if mode_name in {"Classic", "Full Roster"} and has_ownership_targets(pool) else int(target)


def learned_field_proposal_target(platform_name, mode_name, contest, roster_size, target, pool=None):
    return int(np.ceil(target * 1.5)) if learned_field_profiles(platform_name, mode_name, contest, roster_size, pool) else int(target)


def apply_learned_field(field, pool, slots, platform_name, mode_name, contest, target, rng):
    profiles = learned_field_profiles(platform_name, mode_name, contest, len(slots), pool)
    from simmah_field_ownership import has_ownership_targets, calibrate_field_ownership
    ownership_fit = mode_name in {"Classic", "Full Roster"} and has_ownership_targets(pool)
    # Historical construction selection precedes the final ownership fit. It
    # must leave enough independent proposals for selection without replacement.
    history_target = min(len(field), 5 * int(target)) if ownership_fit else target
    selected, provenance = calibrate_field(field, pool, slots, profiles, history_target, rng)
    st.session_state["field_learning_" + platform_name + "_" + mode_name] = provenance
    if provenance.get("applied"):
        st.caption(f"Field learning applied: {provenance['contests']} matching contest(s), {provenance['historical_entries']:,} entries; features: " + ", ".join(provenance["features"]) + ". This calibrates construction, not future player ownership.")
    else:
        st.caption("Field learning: baseline construction used — " + provenance["reason"] + ".")
    if ownership_fit:
        with st.spinner("Calibrating final opponent ownership..."):
            selected, report = calibrate_field_ownership(selected, pool, slots, target, rng)
        diagnostics = selected.attrs.get("ownership_calibration", {})
        mean_error = diagnostics.get("mean_absolute_error_pp", 0)
        max_error = diagnostics.get("max_error_pp", 0)
        st.caption(f"Final ownership calibration: mean error {mean_error:.2f} percentage points; largest difference {max_error:.2f}. Salary frequencies and learned construction targets retained; each generated proposal selected at most once.")
        if max_error > 3:
            st.warning("Some ownership targets cannot be closely matched within the available legal proposals and salary mix. Review the final ownership comparison; projected ownership remains an estimate.")
        with st.expander("Projected versus final opponent ownership", expanded=False):
            st.dataframe(injury_frame(st, report), use_container_width=True, hide_index=True)
            st.download_button("DOWNLOAD OWNERSHIP COMPARISON", report.to_csv(index=False).encode("utf-8"),
                f"{platform_name}_{mode_name.replace(' ', '_')}_Ownership_Comparison.csv", "text/csv",
                key=f"ownership_comparison_download_{platform_name}_{mode_name}", on_click="ignore")
        st.session_state["ownership_comparison_data_" + platform_name + "_" + mode_name] = report
    if selected.attrs.get("construction_distribution") is not None:
        st.caption("Opponent stack/bring-back mix uses matching completed-contest history with verified player metadata; joint construction targets are retained through field calibration. This does not calibrate duplicate counts.")
    return selected


def build_showdown_opponent_field(available_players, simulation_df, players_df,
                                  salary_map, captain_salary_map, salary_cap, target,
                                  progress_bar=None, progress_text=None):
    """Build distinct legal proposals; never feed generated ownership back in."""
    from simmah_showdown_field import build_unique_field
    pool = players_df.drop_duplicates("Name").set_index("Name").reindex(list(available_players)).reset_index()
    pool["Salary"] = pool["Name"].map(salary_map)
    pool["CaptainSalary"] = pool["Name"].map(captain_salary_map)
    means = simulation_df.mean(axis=0).reindex(pool["Name"]).fillna(0).to_numpy(float)
    flex_weights = opponent_field_selection_weights(pool, means)
    points = pd.to_numeric(pool["Projection"], errors="coerce").fillna(0).clip(lower=0).to_numpy(float)
    captain_weights = points ** 2
    # Only supplied/projected CPT ownership is an input. Field CPT Own % is
    # output from an earlier generated field and must not create feedback.
    lookup = {str(c).strip().casefold(): c for c in pool}
    for key in ("projected cpt own %", "projected captain ownership", "captain ownership %", "cpt ownership %"):
        if key in lookup:
            supplied = pd.to_numeric(pool[lookup[key]], errors="coerce")
            valid = supplied.between(0, 100) & np.isfinite(supplied)
            if valid.any() and supplied[valid].sum() > 0:
                fallback = captain_weights / max(captain_weights.sum(), 1e-12) * 100
                captain_weights = np.where(valid, supplied, fallback)
                break
    requested = int(target)
    contest = st.session_state.get("selected_dk_contest", {})
    proposals = learned_field_proposal_target("DraftKings", "Showdown", contest, 6, requested, players_df)
    rng = np.random.default_rng(123)
    def report(fraction, text):
        if progress_bar is not None:
            progress_bar.progress(min(.99, fraction), text=text)
    field = build_unique_field(pool, flex_weights, captain_weights, proposals,
        salary_cap=salary_cap, min_salary=48000, rng=rng, progress=report)
    result = apply_learned_field(field, players_df, ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"],
        "DraftKings", "Showdown", contest, requested, rng)
    result.attrs.update(field.attrs, unique_sample=len(result), requested_unique=requested)
    return result


def expand_showdown_field_by_ownership(sample_field, full_field_size, seed=20261012):
    """Expand the selected field without a second ownership weighting."""
    from simmah_showdown_field import expand_field
    return expand_field(sample_field, full_field_size, seed)



def build_dk_contest_entry_export(entry_df, selected_contest_id, lineup_ids_df, expected_slots, slate_label):
    """Replace roster slots on existing DraftKings entries; never create new contest entries."""
    if entry_df is None or not isinstance(entry_df, pd.DataFrame) or entry_df.empty:
        st.error(
            "To replace lineups in your existing DraftKings contest, upload the CSV from "
            "DraftKings My Contests. Without that entry file, the export cannot target your existing entries."
        )
        return None
    if "Contest ID" not in entry_df.columns or "Entry ID" not in entry_df.columns:
        st.error("Your DraftKings entry file must include Entry ID and Contest ID to replace existing contest entries.")
        return None
    entries = entry_df.copy()
    entries["Contest ID"] = entries["Contest ID"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    target_id = str(selected_contest_id or "").strip()
    if not target_id:
        st.error("Select your contest from the uploaded DraftKings entry file before exporting.")
        return None
    entries = entries[entries["Contest ID"] == target_id].copy().reset_index(drop=True)
    if entries.empty:
        st.error(f"No existing entries found for selected contest ID {target_id}. Choose the contest matching your entry file.")
        return None
    if "Contest Name" in entries.columns:
        entries = entries[entries["Contest Name"].apply(is_full_game_contest_name)].copy().reset_index(drop=True)
    if entries.empty:
        st.error("The selected contest entries were filtered out. Check the contest name and uploaded entry file.")
        return None

    # Locate roster columns in the original entry template, including pandas' .1/.2
    # suffixes for duplicate headers such as FLEX,FLEX or RB,RB.
    original_columns = list(entries.columns)
    normalized = [re.sub(r"\.\d+$", "", str(col).replace("\ufeff", "")).strip().upper() for col in original_columns]
    # DraftKings templates may use repeated RB/WR headers or RB1/RB2 and WR1/WR2/WR3.
    roster_aliases = {
        "RB": {"RB", "RB1", "RB2"},
        "WR": {"WR", "WR1", "WR2", "WR3"},
        "QB": {"QB"}, "TE": {"TE"}, "FLEX": {"FLEX"},
        "DST": {"DST", "D", "DEF"},
        "CPT": {"CPT", "CAPTAIN"}, "CAPTAIN": {"CPT", "CAPTAIN"},
        "MVP": {"MVP"}
    }
    roster_column_indices = []
    used = set()
    for expected in expected_slots:
        accepted_names = roster_aliases.get(expected.upper(), {expected.upper()})
        found = next(
            (i for i, name in enumerate(normalized)
             if i not in used and name in accepted_names),
            None
        )
        if found is None:
            st.error(
                "The uploaded DraftKings entry file does not contain the expected "
                + slate_label + " roster columns (" + ", ".join(expected_slots) + "). Upload the original contest entry CSV."
            )
            return None
        used.add(found)
        roster_column_indices.append(found)

    if lineup_ids_df is None or lineup_ids_df.empty:
        st.error("There are no lineups available to export.")
        return None
    # A replacement export must cover every reserved entry in the selected contest.
    # Never emit a partial file: any omitted Entry ID would keep its old lineup on DraftKings.
    entry_ids = entries["Entry ID"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    invalid_entry_ids = entry_ids.eq("") | entry_ids.str.casefold().eq("nan")
    if invalid_entry_ids.any():
        st.error(
            "The selected DraftKings contest contains one or more blank Entry IDs. "
            "Re-download the original contest entry CSV before exporting replacements."
        )
        return None
    if entry_ids.duplicated().any():
        st.error(
            "The selected DraftKings contest contains duplicate Entry IDs. "
            "Re-download the original contest entry CSV before exporting replacements."
        )
        return None

    entry_count = len(entries)
    lineup_count = len(lineup_ids_df)
    if lineup_count < entry_count:
        st.error(
            f"Replacement export blocked: this contest has {entry_count} reserved entries but only "
            f"{lineup_count} new lineups are available. Build at least {entry_count} new lineups so "
            "every reserved Entry ID is overwritten. No partial replacement file was created."
        )
        return None

    # Export exactly one row per reserved Entry ID for this contest. Extra generated
    # lineups are ignored; no old roster rows or unrelated contest rows are appended.
    count = entry_count
    export_df = entries.copy().reset_index(drop=True)
    export_df["Entry ID"] = entry_ids.reset_index(drop=True)
    ids = lineup_ids_df.iloc[:entry_count].reset_index(drop=True)

    # DraftKings contest-entry replacement CSVs use "Player Name (PlayerID)"
    # in roster cells, not the bare numeric IDs used by the basic lineup upload.
    # Reverse the player map captured from the uploaded DK salary/template CSV.
    dk_player_ids = st.session_state.get("dk_player_ids", {})
    id_to_name = {}
    for player_name, slot_ids in dk_player_ids.items():
        if isinstance(slot_ids, dict):
            for slot_name, player_id in slot_ids.items():
                if player_id:
                    clean_id = str(player_id).strip().removesuffix(".0")
                    id_to_name[(clean_id, str(slot_name).strip().upper())] = str(player_name).strip()

    for j, col_index in enumerate(roster_column_indices):
        slot = str(expected_slots[j]).strip().upper()
        values = []
        for player_id in ids.iloc[:, j].astype(str):
            clean_id = str(player_id).strip().removesuffix(".0")
            player_name = id_to_name.get((clean_id, slot))
            if not player_name:
                # FLEX IDs can be used across repeated FLEX columns; allow any slot mapping.
                player_name = next(
                    (name for (mapped_id, _mapped_slot), name in id_to_name.items()
                     if mapped_id == clean_id),
                    None,
                )
            values.append(f"{player_name} ({clean_id})" if player_name else clean_id)
        export_df.iloc[:, col_index] = values

    # Warn rather than silently creating an incomplete replacement file.
    if id_to_name:
        unresolved = [
            str(export_df.iloc[row_idx, col_index])
            for row_idx in range(count)
            for col_index in roster_column_indices
            if not re.search(r"\(\d+\)$", str(export_df.iloc[row_idx, col_index]).strip())
        ]
        if unresolved:
            st.error(
                "Some exported players could not be matched to DraftKings player names. "
                "Re-upload the correct DraftKings salary/template CSV and export again."
            )
            return None

    st.success(
        f"Export prepared to replace {count} existing DraftKings {slate_label} entry/entries "
        f"in contest {target_id}. Entry IDs and contest metadata are preserved."
    )
    return export_df


def remove_out_players_from_lineups(lineups, slot_columns, label="export"):
    """Final safety filter: never display or export a lineup containing an Out player."""
    if not isinstance(lineups, pd.DataFrame) or lineups.empty:
        return lineups
    statuses = st.session_state.get("player_injury_statuses", {})
    out_names = {
        str(name).strip().casefold()
        for name, status in statuses.items()
        if str(status).strip().casefold() == "out"
    }
    valid_slots = [col for col in slot_columns if col in lineups.columns]
    if not out_names or not valid_slots:
        return lineups
    contains_out = pd.Series(False, index=lineups.index)
    for col in valid_slots:
        contains_out |= lineups[col].astype(str).str.strip().str.casefold().isin(out_names)
    removed = int(contains_out.sum())
    if removed:
        st.warning(f"Removed {removed} {label} lineup(s) containing a player marked Out. Export the refreshed file.")
        return lineups.loc[~contains_out].reset_index(drop=True)
    return lineups


def normalize_injury_player_name(value):
    """Normalize names so injury-feed names match DFS salary-file names."""
    import re
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def normalize_injury_team(value):
    """Normalize team abbreviations and full team names from different DFS files."""
    import re
    raw = re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
    aliases = {
        "arizona": "ari", "arizonacardinals": "ari",
        "atlanta": "atl", "atlantafalcons": "atl",
        "baltimore": "bal", "baltimoreravens": "bal",
        "buffalo": "buf", "buffalobills": "buf",
        "carolina": "car", "carolinapanthers": "car",
        "chicago": "chi", "chicagobears": "chi",
        "cincinnati": "cin", "cincinnatibengals": "cin",
        "cleveland": "cle", "clevelandbrowns": "cle",
        "dallas": "dal", "dallascowboys": "dal",
        "denver": "den", "denverbroncos": "den",
        "detroit": "det", "detroitlions": "det",
        "greenbay": "gb", "greenbaypackers": "gb",
        "houston": "hou", "houstontexans": "hou",
        "indianapolis": "ind", "indianapoliscolts": "ind",
        "jacksonville": "jax", "jacksonvillejaguars": "jax",
        "kansascity": "kc", "kansascitychiefs": "kc",
        "lasvegas": "lv", "lasvegasraiders": "lv",
        "chargers": "lac", "losangeleschargers": "lac",
        "losangelesrams": "lar", "rams": "lar",
        "miami": "mia", "miamidolphins": "mia",
        "minnesota": "min", "minnesotavikings": "min",
        "newengland": "ne", "newenglandpatriots": "ne",
        "neworleans": "no", "neworleanssaints": "no",
        "newyorkgiants": "nyg", "giants": "nyg",
        "newyorkjets": "nyj", "jets": "nyj",
        "philadelphia": "phi", "philadelphiaeagles": "phi",
        "pittsburgh": "pit", "pittsburghsteelers": "pit",
        "sanfrancisco": "sf", "sanfrancisco49ers": "sf",
        "seattle": "sea", "seattleseahawks": "sea",
        "tampa": "tb", "tampabay": "tb", "tampabaybuccaneers": "tb",
        "tennessee": "ten", "tennesseetitans": "ten",
        "washington": "was", "washingtoncommanders": "was", "wsh": "was",
    }
    return aliases.get(raw, raw).upper()


@st.cache_data(ttl=600, show_spinner=False)
def fetch_nfl_injury_statuses():
    """Fetch current NFL injury designations from ESPN; cache for 10 minutes."""
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 UniversalDFSInjurySync/1.0"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload.get("injuries"), list):
            return {}, "ESPN injury feed returned an unexpected response"
    except Exception as exc:
        return {}, "ESPN injury feed unavailable: " + str(exc)[:140]

    statuses = {}
    for team_block in payload.get("injuries", []):
        team_data = team_block.get("team", {}) or {}
        team = normalize_injury_team(team_data.get("abbreviation") or team_data.get("displayName") or team_data.get("name") or team_block.get("displayName") or team_block.get("name"))
        for injury in team_block.get("injuries", []) or []:
            athlete = injury.get("athlete", {}) or {}
            name = normalize_injury_player_name(athlete.get("fullName") or athlete.get("displayName") or athlete.get("shortName"))
            raw_status = str(injury.get("status") or injury.get("shortComment") or injury.get("detail") or "").strip().casefold()
            if not name or not team or not raw_status:
                continue
            if any(word in raw_status for word in ("injured reserve", "reserve/injured", "physically unable to perform", "out", "suspended")):
                status = "Out"
            elif "doubtful" in raw_status:
                status = "Doubtful"
            elif any(word in raw_status for word in ("questionable", "day-to-day", "probable")):
                status = "Questionable"
            else:
                continue
            statuses[(name, team)] = status
    return statuses, "ESPN NFL injury feed"


def apply_injury_statuses(frame, key_prefix):
    """Automatically sync NFL injury statuses and remove Out players from all slate types."""
    from datetime import datetime
    if "player_injury_statuses" not in st.session_state:
        st.session_state["player_injury_statuses"] = {}
    saved_statuses = st.session_state["player_injury_statuses"]
    live_injuries, injury_source = fetch_nfl_injury_statuses()

    injury_snapshot = tuple(sorted((name, team, status) for (name, team), status in live_injuries.items()))
    previous_injury_snapshot = st.session_state.get("injury_feed_snapshot_previous")
    if previous_injury_snapshot is not None and injury_snapshot != previous_injury_snapshot:
        st.session_state["injury_updates_found"] = True
        st.session_state["injury_updates_found_at"] = datetime.now().astimezone().strftime("%Y-%m-%d %I:%M:%S %p %Z")
    st.session_state["injury_feed_snapshot_previous"] = injury_snapshot

    result = frame.copy()
    if "Team" not in result.columns:
        result["Team"] = ""
    result["_injury_name_key"] = result["Name"].map(normalize_injury_player_name)
    result["_injury_team_key"] = result["Team"].map(normalize_injury_team)
    feed_statuses = []
    for _, player_row in result.iterrows():
        feed_statuses.append(live_injuries.get((player_row["_injury_name_key"], player_row["_injury_team_key"])))
    # The live feed is authoritative: a player no longer listed as injured returns to Active.
    result["Injury Status"] = [status or "Active" for status in feed_statuses]
    result.drop(columns=["_injury_name_key", "_injury_team_key"], inplace=True)

    st.caption(f"Injury status updates: {injury_source}. Automatically checks ESPN; data is cached for up to 10 minutes.")
    if st.session_state.get("injury_updates_found"):
        st.warning("NEW INJURY NEWS FOUND — current statuses were refreshed automatically.")
    if not live_injuries and "unavailable" in injury_source.casefold() or not live_injuries and "unexpected" in injury_source.casefold():
        st.warning("Live injury statuses could not be loaded. Do not assume every player is healthy; try syncing again.")
    # Injury news is refreshed together with projections by the shared refresh button.

    out_names = set(result.loc[result["Injury Status"].str.casefold() == "out", "Name"].astype(str).str.strip().str.casefold())
    cache_tokens = (
        "lineup", "portfolio", "simulation", "contest_field", "contest_results",
        "candidate", "exposure", "saved_build", "classic_pool_signature",
        "build_ready", "latest_field_ownership", "fd_active_signature",
        "fd_saved_builds", "fd_lineups"
    )
    def cache_contains_out_player(value):
        if isinstance(value, pd.DataFrame):
            return any(value[column].astype(str).str.strip().str.casefold().isin(out_names).any() for column in value.columns)
        if isinstance(value, dict):
            return any(cache_contains_out_player(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(cache_contains_out_player(item) for item in value)
        return isinstance(value, str) and value.strip().casefold() in out_names

    stale_cache_found = any(
        any(token in str(key).lower() for token in cache_tokens)
        and cache_contains_out_player(value)
        for key, value in list(st.session_state.items())
    )
    if out_names and stale_cache_found:
        clear_tokens = cache_tokens + ("active_slate_signature",)
        preserve_tokens = ("dropdown", "injury_status", "player_injury_statuses", "lineup_mode", "platform", "slate_selector")
        for key in list(st.session_state.keys()):
            if any(token in str(key).lower() for token in clear_tokens) and not any(token in str(key).lower() for token in preserve_tokens):
                st.session_state.pop(key, None)
        st.warning("Saved lineups containing Out players were cleared. Run SIM again to rebuild safely.")

    st.session_state["display_injury_statuses"] = dict(zip(result["Name"].astype(str), result["Injury Status"]))
    questionable = result.loc[result["Injury Status"].str.casefold() == "questionable", "Name"].astype(str).tolist()
    doubtful = result.loc[result["Injury Status"].str.casefold() == "doubtful", "Name"].astype(str).tolist()
    excluded = result.loc[result["Injury Status"].str.casefold() == "out", "Name"].astype(str).tolist()
    st.write("### Automatic Injury Statuses")
    st.caption(f"Out: {len(excluded)} | Questionable: {len(questionable)} | Doubtful: {len(doubtful)}. [Q] = Questionable; [D] = Doubtful. Players listed as Out are automatically removed from the player pool.")
    if questionable:
        st.warning("QUESTIONABLE: " + ", ".join(questionable))
    if excluded:
        st.warning("OUT — automatically excluded: " + ", ".join(excluded))
    result = result[result["Injury Status"].str.casefold() != "out"].reset_index(drop=True)
    if result.empty:
        st.error("All players are marked Out. Check the injury feed and player file before continuing.")
        workspace_stop(st, _loaded_slate_tabs)
    return result


def exclude_zero_projection_players(frame, slate_label):
    """Remove players with missing, invalid, or zero projections before lineup building."""
    if "Projection" not in frame.columns:
        st.error(f"{slate_label}: projection column is missing, so players cannot be safely ranked.")
        workspace_stop(st, _loaded_slate_tabs)
    result = frame.copy()
    result["Projection"] = pd.to_numeric(result["Projection"], errors="coerce")
    excluded = result[
        result["Projection"].isna() |
        ~np.isfinite(result["Projection"]) |
        (result["Projection"] <= 0)
    ]
    if not excluded.empty:
        names = excluded["Name"].astype(str).tolist() if "Name" in excluded.columns else []
        st.warning(
            f"{slate_label}: excluded {len(excluded)} player(s) with zero or missing projections"
            + (": " + ", ".join(names[:20]) if names else "")
            + (" ..." if len(names) > 20 else "")
        )
    result = result[
        result["Projection"].notna() &
        np.isfinite(result["Projection"]) &
        (result["Projection"] > 0)
    ].reset_index(drop=True)
    if result.empty:
        st.error(f"{slate_label}: no players have projections above zero. Check your projection sources.")
        workspace_stop(st, _loaded_slate_tabs)
    return result



def resolve_quarterback_roles_for_build(frame, format_label):
    from simmah_qb_roles import quarterback_conflicts, resolve_quarterbacks
    import hashlib
    conflicts = quarterback_conflicts(frame)
    selected = {}
    unresolved = []
    if conflicts:
        st.warning("Multiple quarterbacks have positive projections for the same team. Confirm each starter; projection size is not starter confirmation.")
        for team, names in conflicts.items():
            token = hashlib.sha256((format_label + team + "|".join(names)).encode()).hexdigest()[:16]
            choice = st.selectbox("Starting QB — " + team, names, index=None,
                placeholder="Confirm the starting quarterback",
                key="confirmed_starting_qb_" + token)
            if choice is None:
                unresolved.append(team)
            else:
                selected[team] = choice
        if unresolved:
            st.info("Select the starting QB for " + ", ".join(unresolved) + " to continue. No game results are used to choose a starter.")
            workspace_stop(st, _loaded_slate_tabs)
    resolved = resolve_quarterbacks(frame, selected)
    position = resolved["Position"].astype(str).str.upper().str.strip()
    signature = tuple(sorted(resolved.loc[position.eq("QB"), ["Team", "Name"]].astype(str).itertuples(index=False, name=None)))
    key = "confirmed_qb_role_signature_" + format_label.replace(" ", "_").lower()
    if st.session_state.get(key) != signature:
        # Clear derived data, never widget values or uploaded files.
        mode = format_label.split(" ", 1)[1].replace(" ", "_").lower()
        data_keys = ["simulation_df", "simulations_ready", "contest_field_df", "contest_field_sample_df",
            "contest_field_ready", "contest_field_count", "candidates_df", "candidates_ready",
            "contest_results_df", "portfolio_df", "final_lineups", "classic_lineups",
            "classic_contest_comparison_df", "classic_contest_entries_df", "classic_contest_field_df",
            "classic_contest_field_ready", "classic_field_context", "saved_builds_by_slate",
            "active_slate_signature", "fd_saved_builds", "fd_full_roster_assigned_portfolio"]
        data_keys += [prefix + mode for prefix in ["fd_lineups_", "fd_simulation_df_",
            "fd_player_sim_", "fd_contest_comparison_", "fd_contest_field_", "fd_active_signature_",
            "fd_assigned_display_", "fd_last_completed_workflow_"]]
        for data_key in data_keys:
            st.session_state.pop(data_key, None)
        st.session_state[key] = signature
    if len(resolved) < len(frame):
        st.caption("Confirmed QB roles applied to candidate and opponent pools. Other projected quarterbacks for those teams are excluded from this run.")
    return resolved





def show_projection_refresh_status(source_files, key_prefix=None):
    """Show one shared refresh control and timestamp across all sites, slates, and formats."""
    import hashlib
    from datetime import datetime


    signatures = []
    for label, uploaded_file in source_files:
        if uploaded_file is None:
            signatures.append((label, None))
        else:
            digest = hashlib.sha256(uploaded_file.getvalue()).hexdigest()
            signatures.append((label, digest))

    # Shared keys prevent separate refresh buttons/timestamps for each format.
    signature_key = "shared_projection_signature"
    time_key = "shared_projection_updated_at"
    current_signature = tuple(signatures)
    if current_signature != st.session_state.get(signature_key):
        st.session_state[signature_key] = current_signature
        if any(digest is not None for _, digest in signatures):
            st.session_state[time_key] = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p %Z")

    updated_at = st.session_state.get(time_key)
    if updated_at:
        st.caption("Last projection refresh: " + updated_at)
    else:
        st.caption("Projection sources have not been refreshed manually yet.")


def normalize_projection_player_name(name):
    """Normalize player names, including position/image prefixes from HTML tables."""
    import re
    value = str(name).casefold().strip()
    value = re.sub(r"\s*\(\d+\)\s*$", "", value)
    # HTML table parsers can include the position and image alt text in the
    # player-name cell (for example, "QB Image Jalen Hurts").
    for _ in range(3):
        value = re.sub(r"^(?:qb|rb|wr|te|dst|def|d|k|flex|flx|cpt|mvp)\s+", "", value)
        value = re.sub(r"^(?:image|img)\s+", "", value)
    value = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", value)
    return re.sub(r"[^a-z0-9]", "", value)


def read_projection_csv(uploaded_file, source_label):
    """Read a DFF or DraftEdge CSV and return normalized player projections."""
    if uploaded_file is None:
        return {}
    import io
    try:
        raw = pd.read_csv(io.BytesIO(uploaded_file.getvalue()), engine="python", on_bad_lines="skip")
        raw.columns = [str(col).strip() for col in raw.columns]
        lookup = {str(col).strip().casefold(): col for col in raw.columns}
        name_col = next((lookup[x] for x in [
            "name", "player", "player name", "nickname", "name + id", "player_name"
        ] if x in lookup), None)
        first_col = next((lookup[x] for x in ["first_name", "first name", "firstname"] if x in lookup), None)
        last_col = next((lookup[x] for x in ["last_name", "last name", "lastname"] if x in lookup), None)
        if name_col is None and first_col is not None and last_col is not None:
            names = raw[first_col].astype(str).str.strip() + " " + raw[last_col].astype(str).str.strip()
        elif name_col is not None:
            names = raw[name_col].astype(str).str.strip()
        else:
            st.warning(f"{source_label}: couldn't find a player-name column in that CSV.")
            return {}
        projection_col = next((lookup[x] for x in [
            "ppg_projection", "projection", "projected points", "projected fantasy points",
            "fantasy points projection", "fpts", "fppg", "proj", "my proj", "total fpts"
        ] if x in lookup), None)
        if projection_col is None:
            st.warning(f"{source_label}: couldn't find a projection column in that CSV.")
            return {}
        values = pd.to_numeric(raw[projection_col].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
        result = {}
        for name, value in zip(names, values):
            key = normalize_projection_player_name(name)
            if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                result[key] = float(value)
        return result
    except Exception as exc:
        st.warning(f"{source_label}: couldn't read the CSV ({exc}).")
        return {}


@st.cache_data(show_spinner=False, ttl=900)
def download_public_projection_table(source_name, platform_name, target_names=None, target_teams=None):
    """Download real projections using the same HTML-table/row attributes tested in Colab."""
    import io
    import re
    from html import unescape
    import requests
    from zoneinfo import ZoneInfo

    target_keys = {
        normalize_projection_player_name(name)
        for name in (target_names or [])
        if normalize_projection_player_name(name)
    }

    expected_teams = {str(team).strip().upper() for team in (target_teams or []) if str(team).strip()}

    def matches_target(projections, page_html=None):
        if target_keys and not target_keys.intersection(projections):
            return False
        if source_name == "DFF" and is_single_game and len(expected_teams) == 2:
            # Shared players alone cannot identify a game (GB vs MIN is not DAL vs GB).
            document = page_html if page_html is not None else response.text
            page_teams = set()
            for tag in re.findall(r"<tr\b[^>]*projections-listing[^>]*>", document, re.IGNORECASE):
                attrs = dict(re.findall(r"([\w-]+)\s*=\s*[\"']([^\"']*)[\"']", tag))
                if attrs.get("data-team"):
                    page_teams.add(attrs["data-team"].strip().upper())
                if attrs.get("data-opp"):
                    page_teams.add(attrs["data-opp"].strip().upper())
            return page_teams == expected_teams
        return True

    platform_key = str(platform_name).casefold()
    is_single_game = "single game" in platform_key or "showdown" in platform_key
    site = "fanduel" if "fanduel" in platform_key else "draftkings"

    # Remember only the verified route, never the projection values. Manual
    # refresh clears the data cache but can fetch this slate directly again.
    route_key = (site, tuple(sorted(target_keys)), tuple(sorted(expected_teams)))
    route_cache = st.session_state.setdefault("verified_dff_slate_routes", {})
    if source_name == "DFF" and is_single_game and target_keys:
        route = route_cache.get(route_key)
        if route:
            try:
                direct = requests.get(route, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
                direct.raise_for_status()
                values = {}
                for tag in re.findall(r"<tr\b[^>]*projections-listing[^>]*>", direct.text, re.IGNORECASE):
                    attrs = dict(re.findall(r"([\w-]+)\s*=\s*[\"']([^\"']*)[\"']", tag))
                    key = normalize_projection_player_name(unescape(attrs.get("data-name", "")))
                    value = pd.to_numeric(attrs.get("data-ppg_proj"), errors="coerce")
                    if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                        values[key] = float(value)
                if len(target_keys.intersection(values)) >= min(2, len(target_keys)) and matches_target(values, direct.text):
                    return values
            except Exception:
                pass
            route_cache.pop(route_key, None)

    # FanDuel Single Game: bypass the legacy Showdown routing entirely. DFF's
    # recent-slates endpoint currently supplies dates without slate IDs, while
    # each dated FanDuel page contains the complete projection table.
    if source_name == "DFF" and site == "fanduel" and is_single_game and target_keys:
        try:
            headers_direct = {"User-Agent": "Mozilla/5.0"}
            sr = requests.get(
                "https://www.dailyfantasyfuel.com/data/slates/recent/nfl/fanduel",
                headers=headers_direct, timeout=30
            )
            sr.raise_for_status()
            payload = sr.json()
            recent_dates = []
            for item in payload.get("dates", []):
                d = str(item.get("start_date", "")).strip()[:10]
                if d and d not in recent_dates:
                    recent_dates.append(d)
            def parse_dff_single_game(html):
                # Source attributes avoid mobile/desktop columns and injury text.
                values = {}
                for tag in re.findall(r"<tr\b[^>]*projections-listing[^>]*>", html, flags=re.IGNORECASE):
                    attrs = dict(re.findall(r"([\w-]+)=[\"']([^\"']*)[\"']", tag))
                    key = normalize_projection_player_name(unescape(attrs.get("data-name", "")))
                    value = pd.to_numeric(attrs.get("data-ppg_proj"), errors="coerce")
                    if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                        values[key] = float(value)
                return values

            from datetime import datetime
            today_et = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
            upcoming_dates = [date for date in recent_dates if date >= today_et]
            recent_dates = sorted(upcoming_dates or recent_dates, reverse=True)
            dff_debug = []
            best_values = {}
            best_overlap = 0
            best_date = None
            from urllib.parse import urljoin
            for slate_date in recent_dates:
                base_url = f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}/"
                page_urls = [base_url]

                # The dated page opens one default matchup. Discover every
                # slate-specific FanDuel Single Game link/candidate first.
                discovery_pages = [base_url]
                discovered_pages = {}
                for discovery_url in discovery_pages:
                    try:
                        discovery = requests.get(discovery_url, headers=headers_direct, timeout=30)
                        discovery.raise_for_status()
                        discovered_pages[discovery_url] = discovery
                    except Exception:
                        continue
                    # DFF populates its slate menu through this AJAX request;
                    # the bare recent endpoint returns dates but no slate codes.
                    code_match = re.search(r"window\.url\s*=\s*['\"]([A-Za-z0-9]+)['\"]", discovery.text)
                    if code_match:
                        try:
                            slate_menu = requests.get(
                                "https://www.dailyfantasyfuel.com/data/slates/recent/nfl/fanduel",
                                params={"date": slate_date, "url": code_match.group(1)},
                                headers=headers_direct, timeout=30,
                            )
                            slate_menu.raise_for_status()
                            for menu_slate in slate_menu.json().get("slates", []):
                                code = str(menu_slate.get("url", ""))
                                if menu_slate.get("showdown_flag") and re.fullmatch(r"[A-Za-z0-9]+", code):
                                    candidate = base_url.rstrip("/") + "?slate=" + code
                                    if candidate not in page_urls:
                                        page_urls.append(candidate)
                        except Exception:
                            pass
                    for href in re.findall(r'href=["\']([^"\']+)["\']', discovery.text, flags=re.IGNORECASE):
                        href_text = unescape(href).strip()
                        low = href_text.casefold()
                        if 'showdown-single-game-projections/fanduel' in low:
                            candidate = urljoin(discovery_url, href_text)
                            if candidate not in page_urls:
                                page_urls.append(candidate)
                    for code in re.findall(r'[?&]slate=([A-Za-z0-9]+)', discovery.text, flags=re.IGNORECASE):
                        candidate = f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}?slate={code}"
                        if candidate not in page_urls:
                            page_urls.append(candidate)

                # Network I/O can overlap; parse and render only on the main
                # Streamlit thread. Reuse the page already fetched for discovery.
                def fetch_candidate_page(page_url):
                    if page_url in discovered_pages:
                        return discovered_pages[page_url]
                    try:
                        candidate_page = requests.get(page_url, headers=headers_direct, timeout=30)
                        candidate_page.raise_for_status()
                        return candidate_page
                    except Exception:
                        return None

                with ThreadPoolExecutor(max_workers=4) as page_executor:
                    pages = list(page_executor.map(fetch_candidate_page, page_urls))
                for page_url, page in zip(page_urls, pages):
                    if page is None:
                        continue
                    values = parse_dff_single_game(page.text)
                    overlap = target_keys.intersection(values)
                    dff_debug.append(f"{slate_date}: url={page_url}, rows={len(values)}, overlap={len(overlap)}")
                    if len(overlap) > best_overlap:
                        best_values = values
                        best_overlap = len(overlap)
                        best_date = slate_date
                        best_url = page_url
            if best_overlap >= min(2, len(target_keys)):
                route_cache[route_key] = best_url
                return best_values

            # DFF does not always expose alternate Single Game slate codes in
            # server-rendered HTML. Fall back to the dated FanDuel classic
            # projection table and keep ONLY uploaded-slate players. This gives
            # Single Game the same DFF player projections without guessing a
            # matchup or hardcoding a slate ID.
            classic_best = {}
            classic_overlap = 0
            classic_date = None
            for slate_date in recent_dates:
                classic_url = f"https://www.dailyfantasyfuel.com/nfl/projections/fanduel/{slate_date}/"
                try:
                    classic_page = requests.get(classic_url, headers=headers_direct, timeout=30)
                    classic_page.raise_for_status()
                    classic_tables = pd.read_html(io.StringIO(classic_page.text))
                except Exception:
                    continue
                for table in classic_tables:
                    if not isinstance(table.columns, pd.MultiIndex) or table.shape[1] <= 7:
                        continue
                    values = {}
                    for name, projection in zip(table.iloc[:, 2], table.iloc[:, 7]):
                        key = normalize_projection_player_name(name)
                        val = pd.to_numeric(projection, errors="coerce")
                        if key in target_keys and pd.notna(val) and np.isfinite(float(val)) and float(val) >= 0:
                            values[key] = float(val)
                    if len(values) > classic_overlap:
                        classic_best = values
                        classic_overlap = len(values)
                        classic_date = slate_date
            if classic_overlap >= min(2, len(target_keys)):
                return classic_best

            st.warning("DFF FanDuel diagnostic — " + ("; ".join(dff_debug) if dff_debug else f"dates={recent_dates!r}; no projection table parsed") + f"; classic_fallback={classic_overlap} matches on {classic_date}")
        except Exception as exc:
            # Surface the real Streamlit-runtime failure instead of silently
            # converting it into an unavailable projection source.
            st.error(f"DFF FanDuel Single Game loader error: {type(exc).__name__}: {exc}")

    if source_name == "DFF":
        if is_single_game:
            # FanDuel's generic page can point at a different slate. The
            # slate-discovery fallback below resolves the actual date + slate
            # identifier and matches it against the uploaded salary names.
            url = (
                "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/"
                if site == "draftkings"
                else "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/"
            )
        else:
            url = "https://www.dailyfantasyfuel.com/nfl/projections/fanduel/" if site == "fanduel" else "https://www.dailyfantasyfuel.com/nfl/projections/"
    elif source_name == "DraftEdge":
        url = "https://draftedge.com/nfl/"
    else:
        return {}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/154.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception:
        if source_name != "DFF" or not is_single_game:
            return {}
        # A failed default matchup must not skip dated/slate discovery.
        from types import SimpleNamespace
        response = SimpleNamespace(text="")

    # DraftEdge's working Colab method: inspect every HTML table and select
    # whichever table has a player column and a projection column.
    try:
        tables = pd.read_html(io.StringIO(response.text))
    except Exception:
        tables = []

    # DFF's working table has two-level headers and three non-player rows.
    # Flatten it the same way as the tested Colab loader before generic parsing.
    if source_name == "DFF":
        for table in tables:
            dff_table = table.copy()
            if isinstance(dff_table.columns, pd.MultiIndex):
                def _dff_header(col):
                    parts = [str(part).strip() for part in col]
                    useful = [
                        part for part in parts
                        if part and not part.casefold().startswith("unnamed:")
                    ]
                    # Prefer the most specific useful header level. On the
                    # current DFF table this yields NAME and FD FP PROJECTED.
                    return useful[-1] if useful else parts[-1]
                dff_table.columns = [_dff_header(col) for col in dff_table.columns]
            else:
                dff_table.columns = [str(col).strip() for col in dff_table.columns]

            normalized_columns = {
                re.sub(r"[^a-z0-9]+", " ", str(col).casefold()).strip(): col
                for col in dff_table.columns
            }
            name_col = next(
                (col for key, col in normalized_columns.items()
                 if key in ("name", "player", "player name", "nickname") or key.endswith(" name")),
                None
            )
            site_prefix = "fd" if site == "fanduel" else "dk"
            proj_col = next(
                (col for key, col in normalized_columns.items()
                 if ("project" in key or "proj" in key)
                 and (site_prefix in key or "fantasy points" in key)),
                None
            )
            if proj_col is None:
                proj_col = next(
                    (col for key, col in normalized_columns.items()
                     if key in ("dk fp projected", "fd fp projected", "ppg projection", "projection")),
                    None
                )
            if name_col is None or proj_col is None:
                continue

            dff_result = {}
            for _, row in dff_table.iterrows():
                key = normalize_projection_player_name(row.get(name_col, ""))
                value = pd.to_numeric(
                    str(row.get(proj_col, "")).replace(",", "").replace("$", ""),
                    errors="coerce"
                )
                if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                    dff_result[key] = float(value)
            if dff_result and matches_target(dff_result):
                return dff_result

    for table in tables:
        table.columns = [str(c).strip() for c in table.columns]
        lookup = {str(col).strip().casefold(): col for col in table.columns}
        name_col = next(
            (col for key, col in lookup.items() if "player" in key or key in ("name", "nickname")),
            None
        )
        proj_col = next(
            (col for key, col in lookup.items()
             if "proj" in key or "projection" in key or key in ("fpts", "fppg")),
            None
        )
        if name_col is None or proj_col is None:
            continue

        result = {}
        for _, row in table.iterrows():
            raw_name = str(row.get(name_col, "")).strip()
            if source_name == "DraftEdge":
                # DraftEdge player cells can include image text, position, and team
                # (for example: "Image Jahmyr Gibbs RB · DET"). Strip those labels
                # before matching against the salary-file player names.
                raw_name = re.sub(r"^(?:image|img)\s+", "", raw_name, flags=re.IGNORECASE)
                raw_name = re.sub(
                    r"\s+(?:QB|RB|WR|TE|DST|DEF|K)\s*[·•|/]\s*[A-Z]{2,4}\s*$",
                    "", raw_name, flags=re.IGNORECASE
                )
                raw_name = re.sub(r"\s+(?:QB|RB|WR|TE|DST|DEF|K)\s*$", "", raw_name, flags=re.IGNORECASE)
            key = normalize_projection_player_name(raw_name)
            value = pd.to_numeric(
                str(row.get(proj_col, "")).replace(",", "").replace("$", ""),
                errors="coerce"
            )
            if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                result[key] = float(value)
        if result and matches_target(result):
            return result

    # DFF's known-working Colab extraction reads projection values from the
    # HTML attributes on each tr.projections-listing row, not visual page text.
    if source_name == "DFF":
        html = response.text
        row_html = re.findall(
            r'<tr\b[^>]*class=["\'][^"\']*projections-listing[^"\']*["\'][^>]*>.*?</tr>',
            html,
            flags=re.IGNORECASE | re.DOTALL
        )
        result = {}
        for row in row_html:
            opening = re.search(r'<tr\b[^>]*>', row, flags=re.IGNORECASE | re.DOTALL)
            opening_tag = opening.group(0) if opening else row

            def attr_value(attr_names, source):
                for attr in attr_names:
                    match = re.search(
                        r'\b' + re.escape(attr) + r'\s*=\s*["\']([^"\']*)["\']',
                        source,
                        flags=re.IGNORECASE
                    )
                    if match:
                        return unescape(match.group(1)).strip()
                return ""

            name = attr_value(("data-player", "data-name"), opening_tag)
            if not name:
                name_match = re.search(
                    r'<div\b[^>]*class=["\'][^"\']*\bbold\b[^"\']*["\'][^>]*>\s*([^<]+)',
                    row,
                    flags=re.IGNORECASE | re.DOTALL
                )
                if name_match:
                    name = unescape(name_match.group(1)).strip()

            projection = attr_value(
                ("data-ppg_proj", "data-ppg-proj", "data-value_proj", "data-projection"),
                row
            )
            key = normalize_projection_player_name(name)
            value = pd.to_numeric(projection, errors="coerce")
            if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                result[key] = float(value)

        if result and matches_target(result):
            return result

        # Current DFF pages may render projections in table cells without the
        # older data-ppg_proj attributes. Fall back to the visible row columns.
        for row in row_html:
            cells = re.findall(r"<td\b([^>]*)>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
            if not cells:
                continue
            cell_texts = []
            projection = None
            for attrs, inner in cells:
                label_match = re.search(
                    r"(?:data-label|aria-label|title|class)=['\"]([^'\"]+)['\"]",
                    attrs,
                    flags=re.IGNORECASE
                )
                label = label_match.group(1).casefold() if label_match else ""
                text_value = unescape(re.sub(r"<[^>]+>", " ", inner))
                text_value = re.sub(r"\s+", " ", text_value).strip()
                cell_texts.append((label, text_value))
                if any(token in label for token in ("ppg_projection", "projection", "projected points", "proj")):
                    parsed = pd.to_numeric(text_value.replace(",", "").replace("$", ""), errors="coerce")
                    if pd.notna(parsed) and np.isfinite(float(parsed)) and float(parsed) > 0:
                        projection = float(parsed)

            name_match = re.search(
                r"<div\b[^>]*class=[^>]*\bbold\b[^>]*>\s*([^<]+)",
                row,
                flags=re.IGNORECASE | re.DOTALL
            )
            name = unescape(name_match.group(1)).strip() if name_match else ""
            if not name:
                opening = re.search(r"<tr\b[^>]*>", row, flags=re.IGNORECASE | re.DOTALL)
                opening_tag = opening.group(0) if opening else row
                name = attr_value(("data-player", "data-name"), opening_tag)

            # On the current DFF layout the visible cells are position, player,
            # salary, team, opponent, recent average, projection, then value.
            if projection is None and len(cell_texts) > 6:
                parsed = pd.to_numeric(
                    cell_texts[6][1].replace(",", "").replace("$", ""),
                    errors="coerce"
                )
                if pd.notna(parsed) and np.isfinite(float(parsed)) and float(parsed) > 0:
                    projection = float(parsed)

            key = normalize_projection_player_name(name)
            if key and projection is not None:
                result[key] = projection

        if result and matches_target(result):
            return result

        # Some DFF pages put the same attributes on elements outside table rows.
        for match in re.finditer(
            r'data-ppg_proj=["\']([^"\']+)["\'].*?data-player_id=["\'][^"\']+["\'].*?<div class=["\']bold["\']>\s*([^<]+)',
            html,
            flags=re.IGNORECASE | re.DOTALL
        ):
            projection, name = match.groups()
            key = normalize_projection_player_name(unescape(name).strip())
            value = pd.to_numeric(projection, errors="coerce")
            if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                result[key] = float(value)
        if result and matches_target(result):
            return result

        # DFF's generic single-game page opens one default matchup.  Before
        # falling back to date guessing, follow every slate-specific Showdown
        # link exposed by that page and keep the first table that intersects the
        # salary-file player names.  This makes the selected DK/FD game drive
        # the DFF match instead of whichever game DFF happens to show by default.
        if is_single_game and target_keys:
            try:
                from urllib.parse import urljoin
                slate_links = []
                for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
                    href_text = unescape(href).strip()
                    if 'showdown-single-game-projections' not in href_text.casefold():
                        continue
                    if site == 'fanduel' and '/fanduel' not in href_text.casefold():
                        continue
                    if site == 'draftkings' and '/fanduel' in href_text.casefold():
                        continue
                    candidate = urljoin(url, href_text)
                    if candidate != url and candidate not in slate_links:
                        slate_links.append(candidate)

                for slate_url in slate_links:
                    try:
                        slate_page = requests.get(slate_url, headers=headers, timeout=30)
                        slate_page.raise_for_status()
                        slate_tables = pd.read_html(io.StringIO(slate_page.text))
                    except Exception:
                        continue

                    for slate_table in slate_tables:
                        candidate_table = slate_table.copy()
                        if isinstance(candidate_table.columns, pd.MultiIndex):
                            def _dff_candidate_header(col):
                                parts = [str(part).strip() for part in col]
                                useful = [
                                    part for part in parts
                                    if part and not part.casefold().startswith("unnamed:")
                                ]
                                return useful[-1] if useful else parts[-1]
                            candidate_table.columns = [
                                _dff_candidate_header(col) for col in candidate_table.columns
                            ]
                        else:
                            candidate_table.columns = [str(col).strip() for col in candidate_table.columns]

                        normalized_columns = {
                            re.sub(r'[^a-z0-9]+', ' ', str(col).casefold()).strip(): col
                            for col in candidate_table.columns
                        }
                        name_col = next(
                            (col for key, col in normalized_columns.items()
                             if key in ('name', 'player', 'player name', 'nickname') or key.endswith(' name')),
                            None
                        )
                        site_prefix = 'fd' if site == 'fanduel' else 'dk'
                        proj_col = next(
                            (col for key, col in normalized_columns.items()
                             if ('project' in key or 'proj' in key)
                             and (site_prefix in key or 'fantasy points' in key)),
                            None
                        )
                        if proj_col is None:
                            proj_col = next(
                                (col for key, col in normalized_columns.items()
                                 if key in ('dk fp projected', 'fd fp projected', 'ppg projection', 'projection')),
                                None
                            )
                        if name_col is None or proj_col is None:
                            continue

                        slate_result = {}
                        for _, slate_row in candidate_table.iterrows():
                            player_key = normalize_projection_player_name(slate_row.get(name_col, ''))
                            player_value = pd.to_numeric(
                                str(slate_row.get(proj_col, '')).replace(',', '').replace('$', ''),
                                errors='coerce'
                            )
                            if (player_key and pd.notna(player_value)
                                    and np.isfinite(float(player_value)) and float(player_value) >= 0):
                                slate_result[player_key] = float(player_value)

                        # Require a meaningful overlap so one shared/ambiguous
                        # player name cannot select the wrong matchup.
                        overlap = target_keys.intersection(slate_result)
                        required_overlap = min(2, len(target_keys))
                        if slate_result and len(overlap) >= required_overlap and matches_target(slate_result, slate_page.text):
                            return slate_result
            except Exception:
                pass

        # DFF slate API can expose multiple games on the same date.  The old
        # fallback only kept start_date and therefore always opened the first
        # game for that date.  Collect slate/url identifiers too, then test each
        # date+slate combination against the salary-file player names.
        if is_single_game and target_keys:
            try:
                from datetime import date
                from urllib.parse import quote

                slate_response = requests.get(
                    f"https://www.dailyfantasyfuel.com/data/slates/recent/nfl/{site}",
                    headers=headers,
                    timeout=30
                )
                slate_response.raise_for_status()
                slate_payload = slate_response.json()

                candidates = []

                def collect_slate_candidates(node, inherited_date=''):
                    if isinstance(node, dict):
                        node_date = str(
                            node.get('start_date') or node.get('date') or inherited_date or ''
                        ).strip()[:10]
                        slate_code = str(
                            node.get('slate') or node.get('url') or node.get('url_code')
                            or node.get('code') or ''
                        ).strip()
                        if node_date:
                            item = (node_date, slate_code)
                            if item not in candidates:
                                candidates.append(item)
                        for value in node.values():
                            collect_slate_candidates(value, node_date)
                    elif isinstance(node, list):
                        for value in node:
                            collect_slate_candidates(value, inherited_date)

                collect_slate_candidates(slate_payload)
                # The bare API returns dates with an EMPTY slates list.
                # Its AJAX menu requires both date and the page's window.url.
                # Without that request every date opens only its first game.
                from datetime import datetime, timedelta
                current_date = datetime.now(ZoneInfo("America/New_York")).date()
                valid_dates = sorted({d for d, _ in candidates
                                      if current_date.isoformat() <= d <= (current_date + timedelta(days=7)).isoformat()})
                candidates = [(d, code) for d, code in candidates if d in valid_dates]
                preferred_codes = set()
                selected_name = str(st.session_state.get("selected_dk_contest", {}).get("name", "")).upper()
                matchup = re.search(r"\(([A-Z]{2,3})\s*@\s*([A-Z]{2,3})\)", selected_name)
                preferred_teams = expected_teams or (set(matchup.groups()) if matchup and site == "draftkings" else set())
                for slate_date in valid_dates:
                    discovery_url = (f"https://www.dailyfantasyfuel.com/nfl/"
                                     f"showdown-single-game-projections/{site}/{slate_date}/")
                    try:
                        discovery = requests.get(discovery_url, headers=headers, timeout=30)
                        discovery.raise_for_status()
                        code_match = re.search(r"window\.url\s*=\s*['\"]([A-Za-z0-9]+)['\"]", discovery.text)
                        if not code_match:
                            continue
                        menu = requests.get(
                            f"https://www.dailyfantasyfuel.com/data/slates/recent/nfl/{site}",
                            params={"date": slate_date, "url": code_match.group(1)},
                            headers=headers, timeout=30,
                        )
                        menu.raise_for_status()
                        for item in menu.json().get("slates", []):
                            code = str(item.get("url", ""))
                            if item.get("showdown_flag") and re.fullmatch(r"[A-Za-z0-9]+", code):
                                candidate = (slate_date, code)
                                if candidate not in candidates:
                                    candidates.append(candidate)
                                menu_teams = set(re.findall(r"\b[A-Z]{2,3}\b", str(item.get("slate_type", "")).upper()))
                                if preferred_teams and menu_teams == preferred_teams:
                                    preferred_codes.add(candidate)
                    except Exception:
                        continue
                today = current_date.isoformat()
                candidates.sort(key=lambda item: (item not in preferred_codes, item[0] < today, item[0], item[1]))

                def parse_dff_candidate(candidate_html):
                    candidate_result = {}
                    candidate_rows = re.findall(
                        r"<tr\b[^>]*class=['\"][^'\"]*projections-listing[^'\"]*['\"][^>]*>.*?</tr>",
                        candidate_html,
                        flags=re.IGNORECASE | re.DOTALL
                    )
                    for candidate_row in candidate_rows:
                        opening = re.search(r'<tr\b[^>]*>', candidate_row, flags=re.IGNORECASE | re.DOTALL)
                        opening_tag = opening.group(0) if opening else candidate_row

                        def candidate_attr(attrs, source):
                            for attr in attrs:
                                match = re.search(
                                    r"\b" + re.escape(attr) + r"\s*=\s*['\"]([^'\"]*)['\"]",
                                    source,
                                    flags=re.IGNORECASE
                                )
                                if match:
                                    return unescape(match.group(1)).strip()
                            return ''

                        name = candidate_attr(('data-player', 'data-name'), opening_tag)
                        if not name:
                            name_match = re.search(
                                r"<div\b[^>]*class=['\"][^'\"]*\bbold\b[^'\"]*['\"][^>]*>\s*([^<]+)",
                                candidate_row,
                                flags=re.IGNORECASE | re.DOTALL
                            )
                            if name_match:
                                name = unescape(name_match.group(1)).strip()
                        projection = candidate_attr(
                            ('data-ppg_proj', 'data-ppg-proj', 'data-value_proj', 'data-projection'),
                            candidate_row
                        )
                        value = pd.to_numeric(projection, errors='coerce')

                        if pd.isna(value):
                            cells = re.findall(
                                r'<td\b[^>]*>(.*?)</td>', candidate_row,
                                flags=re.IGNORECASE | re.DOTALL
                            )
                            if len(cells) > 6:
                                visible = unescape(re.sub(r'<[^>]+>', ' ', cells[6]))
                                visible = re.sub(r'\s+', ' ', visible).strip()
                                value = pd.to_numeric(
                                    visible.replace(',', '').replace('$', ''), errors='coerce'
                                )

                        key = normalize_projection_player_name(name)
                        if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                            candidate_result[key] = float(value)
                    return candidate_result

                for slate_date, slate_code in candidates:
                    # DFF's FanDuel slate URLs use the regular projections route,
                    # e.g. /nfl/projections/fanduel/YYYY-MM-DD?slate=SLATE_ID.
                    # The old code incorrectly tried the showdown route and could
                    # never reach a valid FD slate such as DAL-GB.
                    if site == 'fanduel':
                        base = (
                            f"https://www.dailyfantasyfuel.com/nfl/"
                            f"projections/fanduel/{slate_date}"
                        )
                    else:
                        base = (
                            f"https://www.dailyfantasyfuel.com/nfl/"
                            f"showdown-single-game-projections/{site}/{slate_date}"
                        )
                    candidate_urls = []
                    if slate_code:
                        encoded = quote(slate_code, safe='')
                        candidate_urls.extend([
                            f"{base}?slate={encoded}",
                            f"{base}?url={encoded}",
                        ])
                    candidate_urls.append(base + '/')

                    for candidate_url in candidate_urls:
                        try:
                            candidate_response = requests.get(candidate_url, headers=headers, timeout=30)
                            candidate_response.raise_for_status()
                        except Exception:
                            continue
                        candidate_result = parse_dff_candidate(candidate_response.text)
                        try:
                            candidate_tables = pd.read_html(io.StringIO(candidate_response.text))
                        except Exception:
                            candidate_tables = []
                        for candidate_table in candidate_tables:
                            candidate_table = candidate_table.copy()
                            if isinstance(candidate_table.columns, pd.MultiIndex):
                                def _candidate_header(col):
                                    parts = [str(part).strip() for part in col]
                                    useful = [part for part in parts if part and not part.casefold().startswith("unnamed:")]
                                    return useful[-1] if useful else parts[-1]
                                candidate_table.columns = [_candidate_header(col) for col in candidate_table.columns]
                            else:
                                candidate_table.columns = [str(col).strip() for col in candidate_table.columns]
                            normalized = {
                                re.sub(r"[^a-z0-9]+", " ", str(col).casefold()).strip(): col
                                for col in candidate_table.columns
                            }
                            candidate_name_col = next(
                                (col for key, col in normalized.items()
                                 if key in ("name", "player", "player name", "nickname") or key.endswith(" name")),
                                None
                            )
                            candidate_site_prefix = "fd" if site == "fanduel" else "dk"
                            candidate_proj_col = next(
                                (col for key, col in normalized.items()
                                 if ("project" in key or "proj" in key)
                                 and (candidate_site_prefix in key or "fantasy points" in key)),
                                None
                            )
                            if candidate_name_col is None or candidate_proj_col is None:
                                continue
                            for _, candidate_row in candidate_table.iterrows():
                                player_key = normalize_projection_player_name(candidate_row.get(candidate_name_col, ""))
                                player_value = pd.to_numeric(
                                    str(candidate_row.get(candidate_proj_col, "")).replace(",", "").replace("$", ""),
                                    errors="coerce"
                                )
                                if player_key and pd.notna(player_value) and np.isfinite(float(player_value)) and float(player_value) >= 0:
                                    candidate_result[player_key] = float(player_value)
                            if candidate_result:
                                break
                        overlap = target_keys.intersection(candidate_result)
                        required_overlap = min(2, len(target_keys))
                        if candidate_result and len(overlap) >= required_overlap and matches_target(candidate_result, candidate_response.text):
                            route_cache[route_key] = candidate_url
                            return candidate_result
            except Exception:
                pass

        # Showdown pages need the slate date in the URL. The Colab notebook
        # confirmed this route works; discover upcoming slate dates from DFF.
        if is_single_game:
            try:
                from datetime import date
                slate_response = requests.get(
                    f"https://www.dailyfantasyfuel.com/data/slates/recent/nfl/{site}",
                    headers=headers,
                    timeout=30
                )
                slate_response.raise_for_status()
                slate_payload = slate_response.json()
                dates = sorted({
                    str(item.get("start_date", ""))
                    for item in slate_payload.get("dates", [])
                    if item.get("start_date")
                })
                today = date.today().isoformat()
                dates = [d for d in dates if d >= today] + [d for d in dates if d < today]
                for slate_date in dates:
                    dated_url = (
                        f"https://www.dailyfantasyfuel.com/nfl/"
                        f"showdown-single-game-projections/{site}/{slate_date}/"
                    )
                    try:
                        dated_response = requests.get(dated_url, headers=headers, timeout=30)
                        dated_response.raise_for_status()
                    except Exception:
                        continue
                    dated_html = dated_response.text
                    dated_rows = re.findall(
                        r"<tr\b[^>]*class=['\"][^'\"]*projections-listing[^'\"]*['\"][^>]*>.*?</tr>",
                        dated_html,
                        flags=re.IGNORECASE | re.DOTALL
                    )
                    dated_result = {}
                    for row in dated_rows:
                        opening = re.search(r'<tr\b[^>]*>', row, flags=re.IGNORECASE | re.DOTALL)
                        opening_tag = opening.group(0) if opening else row

                        def dated_attr(attrs, source):
                            for attr in attrs:
                                m = re.search(
                                    r"\b" + re.escape(attr) + r"\s*=\s*['\"]([^'\"]*)['\"]",
                                    source,
                                    flags=re.IGNORECASE
                                )
                                if m:
                                    return unescape(m.group(1)).strip()
                            return ""

                        name = dated_attr(("data-player", "data-name"), opening_tag)
                        if not name:
                            nm = re.search(
                                r"<div\b[^>]*class=['\"][^'\"]*\bbold\b[^'\"]*['\"][^>]*>\s*([^<]+)",
                                row,
                                flags=re.IGNORECASE | re.DOTALL
                            )
                            if nm:
                                name = unescape(nm.group(1)).strip()
                        proj = dated_attr(
                            ("data-ppg_proj", "data-ppg-proj", "data-value_proj", "data-projection"),
                            row
                        )
                        key = normalize_projection_player_name(name)
                        value = pd.to_numeric(proj, errors="coerce")
                        if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                            dated_result[key] = float(value)
                    if dated_result and matches_target(dated_result, dated_html):
                        return dated_result
            except Exception:
                pass

    # Final FanDuel single-game fallback: DFF's recent-slates API currently
    # returns dates but an empty slates array. The plain dated FanDuel page
    # still contains the full projection table, so parse each recent date
    # directly and select the one overlapping the uploaded salary names.
    if source_name == "DFF" and site == "fanduel" and is_single_game and target_keys:
        try:
            slate_response = requests.get(
                "https://www.dailyfantasyfuel.com/data/slates/recent/nfl/fanduel",
                headers=headers, timeout=30
            )
            slate_response.raise_for_status()
            payload = slate_response.json()
            recent_dates = []
            for item in payload.get("dates", []):
                slate_date = str(item.get("start_date", "")).strip()[:10]
                if slate_date and slate_date not in recent_dates:
                    recent_dates.append(slate_date)
            for slate_date in reversed(recent_dates):
                dated_url = f"https://www.dailyfantasyfuel.com/nfl/projections/fanduel/{slate_date}/"
                try:
                    dated_response = requests.get(dated_url, headers=headers, timeout=30)
                    dated_response.raise_for_status()
                    dated_tables = pd.read_html(io.StringIO(dated_response.text))
                except Exception:
                    continue
                for dated_table in dated_tables:
                    if not isinstance(dated_table.columns, pd.MultiIndex):
                        continue
                    name_col = None
                    projection_col = None
                    for col in dated_table.columns:
                        levels = [
                            re.sub(r"[^a-z0-9]+", " ", str(part).casefold()).strip()
                            for part in col
                            if not str(part).casefold().startswith("unnamed:")
                        ]
                        if "name" in levels:
                            name_col = col
                        if any(level == "fd fp projected" for level in levels):
                            projection_col = col
                    if name_col is None or projection_col is None:
                        continue
                    dated_result = {}
                    for name, projection in zip(dated_table[name_col], dated_table[projection_col]):
                        key = normalize_projection_player_name(name)
                        value = pd.to_numeric(projection, errors="coerce")
                        if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                            dated_result[key] = float(value)
                    overlap = target_keys.intersection(dated_result)
                    if dated_result and len(overlap) >= min(2, len(target_keys)):
                        return dated_result
        except Exception:
            pass

    # Final FanDuel single-game fallback: DFF's recent-slates API currently
    # returns dates but an empty slates array. The plain dated FanDuel page
    # still contains the full projection table, so parse each recent date
    # directly and select the one overlapping the uploaded salary names.
    if source_name == "DFF" and site == "fanduel" and is_single_game and target_keys:
        try:
            slate_response = requests.get(
                "https://www.dailyfantasyfuel.com/data/slates/recent/nfl/fanduel",
                headers=headers, timeout=30
            )
            slate_response.raise_for_status()
            payload = slate_response.json()
            recent_dates = []
            for item in payload.get("dates", []):
                slate_date = str(item.get("start_date", "")).strip()[:10]
                if slate_date and slate_date not in recent_dates:
                    recent_dates.append(slate_date)
            for slate_date in reversed(recent_dates):
                dated_url = f"https://www.dailyfantasyfuel.com/nfl/projections/fanduel/{slate_date}/"
                try:
                    dated_response = requests.get(dated_url, headers=headers, timeout=30)
                    dated_response.raise_for_status()
                    dated_tables = pd.read_html(io.StringIO(dated_response.text))
                except Exception:
                    continue
                for dated_table in dated_tables:
                    if not isinstance(dated_table.columns, pd.MultiIndex):
                        continue
                    name_col = None
                    projection_col = None
                    for col in dated_table.columns:
                        levels = [
                            re.sub(r"[^a-z0-9]+", " ", str(part).casefold()).strip()
                            for part in col
                            if not str(part).casefold().startswith("unnamed:")
                        ]
                        if "name" in levels:
                            name_col = col
                        if any(level == "fd fp projected" for level in levels):
                            projection_col = col
                    if name_col is None or projection_col is None:
                        continue
                    dated_result = {}
                    for name, projection in zip(dated_table[name_col], dated_table[projection_col]):
                        key = normalize_projection_player_name(name)
                        value = pd.to_numeric(projection, errors="coerce")
                        if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                            dated_result[key] = float(value)
                    overlap = target_keys.intersection(dated_result)
                    if dated_result and len(overlap) >= min(2, len(target_keys)):
                        return dated_result
        except Exception:
            pass

    return {}

def refresh_public_projection_sources(platform_names=None):
    """Check selected format by default to avoid slow multi-format cold starts."""
    status = {}
    snapshots = {}
    selected_platforms = tuple(platform_names or (
        "DraftKings Classic", "DraftKings Showdown",
        "FanDuel Full Roster", "FanDuel Single Game"
    ))
    for platform_name in selected_platforms:
        for source_name in ("DFF", "DraftEdge"):
            values = download_public_projection_table(source_name, platform_name)
            loaded = bool(values)
            label = f"{source_name} ({platform_name})"
            status[label] = loaded
            if loaded:
                snapshots[label] = tuple(sorted(
                    (str(player), round(float(points), 3))
                    for player, points in values.items()
                ))
            # Streamlit caches empty returns too; clear failed keys so the next
            # rerun can retry immediately instead of preserving a failed fetch.
            if not loaded:
                try:
                    download_public_projection_table.clear(source_name, platform_name)
                except Exception:
                    pass
    st.session_state["automatic_projection_snapshot_current"] = snapshots
    return status


@st.fragment(run_every="30m")
def automatic_projection_refresh(platform_name):
    """Check only the active format at most once every 30 minutes, even across full app reruns."""
    from datetime import datetime, timedelta
    now_dt = datetime.now(ZoneInfo("America/New_York"))
    throttle_key = "automatic_projection_last_check_" + str(platform_name).strip().casefold().replace(" ", "_")
    last_check = st.session_state.get(throttle_key)
    should_refresh = True
    if isinstance(last_check, datetime):
        should_refresh = (now_dt - last_check) >= timedelta(minutes=30)

    if should_refresh:
        status = refresh_public_projection_sources((platform_name,))
        st.session_state[throttle_key] = now_dt
        st.session_state["automatic_projection_last_status_" + str(platform_name)] = status
    else:
        status = st.session_state.get(
            "automatic_projection_last_status_" + str(platform_name), {}
        )

    effective_check = st.session_state.get(throttle_key, now_dt)
    now = effective_check.strftime("%Y-%m-%d %I:%M:%S %p %Z")
    current_snapshot = st.session_state.get("automatic_projection_snapshot_current", {})
    previous_snapshot = st.session_state.get("automatic_projection_snapshot_previous")
    if previous_snapshot is not None and current_snapshot != previous_snapshot:
        st.session_state["projection_updates_found"] = True
        st.session_state["projection_updates_found_at"] = now
    st.session_state["automatic_projection_snapshot_previous"] = current_snapshot
    st.session_state["automatic_projection_refresh_time"] = now
    st.session_state["automatic_projection_refresh_status"] = status

    # This function runs as a Streamlit fragment every 30 minutes, so update the
    # button styling here too when new projection or injury data is detected.
    if st.session_state.get("projection_updates_found") or st.session_state.get("injury_updates_found"):
        st.markdown(
            """
            <style>
            .st-key-sticky_projection_bar button {
                background-color: #d62828 !important;
                border-color: #d62828 !important;
                color: #ffffff !important;
            }
            .st-key-sticky_projection_bar button:hover {
                background-color: #b71c1c !important;
                border-color: #b71c1c !important;
                color: #ffffff !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    successful = [name for name, loaded in status.items() if loaded]
    if successful:
        st.caption("Automatic projection check: " + ", ".join(successful) + ". Last checked: " + now)
    else:
        st.warning("Automatic projection check could not load any public projection tables. It will try again in 30 minutes.")



def get_projection_source_data(uploaded_file, source_name, platform_name, target_names=None, target_teams=None):
    uploaded = read_projection_csv(uploaded_file, source_name)
    if uploaded:
        return uploaded, "uploaded CSV"
    downloaded = download_public_projection_table(source_name, platform_name, target_names=target_names, target_teams=target_teams)
    return downloaded, "automatic download" if downloaded else "unavailable"

@st.cache_data(show_spinner=False, ttl=900)
def download_rotowire_projections(platform_name, target_teams, slate_dates):
    from simmah_rotowire import download
    return download(platform_name, target_teams, slate_dates)


def apply_external_projection_sources(players_frame, dff_file, draftedge_file, platform_name='DraftKings'):
    """Average every available external projection; never substitute internal estimates."""
    result = players_frame.copy()
    target_names = result["Name"].astype(str).tolist() if "Name" in result.columns else []
    target_teams = tuple(sorted(result["Team"].dropna().astype(str).str.upper().unique())) if "Team" in result.columns else ()
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names, target_teams)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names, target_teams)
    rotowire, rotowire_status = {}, "skipped: uploaded CSV priority"
    if dff_file is None and draftedge_file is None:
        from simmah_rotowire import salary_dates
        from datetime import datetime
        dates = salary_dates(result)
        date_note = ""
        if not dates:
            dates = (datetime.now(ZoneInfo("America/New_York")).date().isoformat(),)
            date_note = "; salary file undated, matching today's games only"
        try:
            rotowire, rw_slate = download_rotowire_projections(platform_name, target_teams, dates)
            rotowire_status = "automatic download, slate " + rw_slate + date_note
        except Exception:
            rotowire_status = "unavailable: no verified matching slate or download failed" + date_note
    source_maps = (("DFF", dff), ("DraftEdge", draftedge), ("RotoWire", rotowire))
    match_counts = {name: 0 for name, _ in source_maps}
    projections, sources = [], []
    averaged = missing_external = 0

    defense_names = dict(zip(
        "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LAR MIA MIN NE NO NYG NYJ PHI PIT SF SEA TB TEN WAS".split(),
        "Cardinals Falcons Ravens Bills Panthers Bears Bengals Browns Cowboys Broncos Lions Packers Texans Colts Jaguars Chiefs Raiders Chargers Rams Dolphins Vikings Patriots Saints Giants Jets Eagles Steelers 49ers Seahawks Buccaneers Titans Commanders".split(),
    ))

    for _, row in result.iterrows():
        key = normalize_projection_player_name(row.get("Name", ""))
        available = []
        for source_name, values in source_maps:
            value = values.get(key)
            if value is None and str(row.get("Position", "")).upper() in ("D", "DST", "DEF"):
                nickname = defense_names.get(str(row.get("Team", "")).upper(), "")
                value = values.get(normalize_projection_player_name(nickname))
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(value) and value > 0:
                available.append((source_name, value))
                match_counts[source_name] += 1
        if available:
            value = float(np.mean([v for _, v in available]))
            source = " + ".join(name for name, _ in available)
            if len(available) > 1:
                source += " average"
                averaged += 1
        else:
            value, source = np.nan, "No external projection"
            missing_external += 1
        projections.append(value)
        sources.append(source)

    result["Projection"] = pd.to_numeric(pd.Series(projections, index=result.index), errors="coerce")
    result["ProjectionSource"] = sources
    st.caption(
        f"External projection matches: DFF {match_counts['DFF']}; "
        f"DraftEdge {match_counts['DraftEdge']}; RotoWire {match_counts['RotoWire']}; averaged {averaged}; missing {missing_external}. "
        f"DFF: {dff_status}; DraftEdge: {draftedge_status}; RotoWire: {rotowire_status}. "
        "Internal estimates are disabled. Players without a valid external projection, including zero projections, "
        "are removed from the lineup pool."
    )
    return result

def normalize_simulation_cache_name(name):
    """Normalize player names for session-only simulated projection matching."""
    import re
    value = str(name).casefold().strip()
    value = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", value)
    return re.sub(r"[^a-z0-9]", "", value)


def build_opponent_map(source_df, team_values):
    """Map each NFL team to its opponent using matchup data when available."""
    import re

    teams = {
        str(team).strip().upper()
        for team in team_values
        if str(team).strip() and str(team).strip().lower() != "nan"
    }
    opponents = {}

    if source_df is not None:
        lookup = {str(col).strip().casefold(): col for col in source_df.columns}
        game_info_col = lookup.get("game info") or lookup.get("gameinfo")
        if game_info_col is not None:
            for game_info in source_df[game_info_col].dropna().astype(str):
                match = re.search(r"([A-Z]{2,3})\s*@\s*([A-Z]{2,3})", game_info.upper())
                if match:
                    away, home = match.groups()
                    opponents[away] = home
                    opponents[home] = away

    # For single-game files without a Game Info column, use the two teams present.
    if not opponents and len(teams) == 2:
        first, second = sorted(teams)
        opponents[first] = second
        opponents[second] = first

    return opponents



def full_roster_contest_parameters(contest, representative_count):
    """Resolve explicit contest metadata; keep the existing Hail Mary preset."""
    contest = contest or {}
    owned = max(1, int(contest.get("your_entries") or 1))
    tiers = contest.get("payouts") or contest.get("payout_tiers")
    field_size = int(contest.get("field_size") or 0)
    preset = "45K Sun NFL Hail Mary" in str(contest.get("name", ""))
    if preset:
        tiers = tiers or [(1, 1, 2000.0), (2, 2, 1000.0), (3, 3, 750.0), (4, 4, 500.0), (5, 5, 300.0), (6, 6, 200.0), (7, 7, 150.0), (8, 8, 125.0), (9, 10, 100.0), (11, 12, 75.0), (13, 15, 50.0), (16, 20, 30.0), (21, 25, 20.0), (26, 30, 15.0), (31, 40, 10.0), (41, 50, 7.5), (51, 75, 5.0), (76, 100, 4.0), (101, 150, 3.0), (151, 300, 2.0), (301, 600, 1.5), (601, 1000, 1.25), (1001, 3000, 1.0), (3001, 7500, 0.8), (7501, 15000, 0.7), (15001, 30000, 0.6), (30001, 65000, 0.5)]
        field_size = max(215568, field_size)
    # Confirmed by the user's prize-table screenshot for this exact contest.
    # Use capacity as the modeled final field; current entry count is not final.
    if str(contest.get("id", "")) == "135464-281110099":
        tiers = tiers or [[1,1,200],[2,2,100],[3,3,50],[4,4,30],[5,5,25],[6,6,20],[7,7,15],[8,8,12],[9,10,10],[11,12,8],[13,15,6],[16,20,4],[21,25,3],[26,30,2],[31,40,1.5],[41,50,1],[51,75,0.75],[76,100,0.5],[101,150,0.4],[151,250,0.35],[251,500,0.3],[501,1000,0.25],[1001,2255,0.2],[2256,5000,0.15],[5001,10000,0.12],[10001,28750,0.1]]
        field_size = field_size or 95808
        contest = dict(contest, entry_fee=0.05 if contest.get("entry_fee") is None else contest["entry_fee"])
    # Screenshot-verified schedule, bound to the entry template's exact contest ID.
    if str(contest.get("id", "")) == "135541-281148543":
        tiers = [(1,1,500),(2,2,250),(3,3,150),(4,4,100),(5,5,75),(6,6,50),
            (7,7,40),(8,8,30),(9,10,25),(11,15,20),(16,20,15),(21,30,12),
            (31,40,10),(41,50,8),(51,75,6),(76,100,5),(101,150,4),(151,210,3),
            (211,400,2.5),(401,600,2),(601,1000,1.5),(1001,1500,1.25),
            (1501,3000,1),(3001,6000,.75),(6001,10000,.6),(10001,28750,.5)]
        field_size = 95808
        contest = dict(contest, entry_fee=0.25)
    known_field = field_size > owned
    field_size = max(field_size, int(representative_count) + owned) if not known_field else field_size
    return {"field_size": field_size, "owned": owned, "tiers": tiers or [],
        "fee": float(contest.get("entry_fee") or 0),
        "payouts_known": bool(tiers) and known_field and contest.get("entry_fee") is not None}

@st.cache_resource(show_spinner=False, max_entries=2)
def showdown_sorted_field_cached(outcomes, field_indices, multiplier, start, end):
    """Reuse opponent scores across portfolio changes, backed by temporary disk."""
    import tempfile
    from pathlib import Path
    owner = tempfile.TemporaryDirectory(prefix="simmah-field-")
    path = Path(owner.name) / "sorted.npy"
    result = None
    for offset in range(start, end, 128):
        stop = min(offset + 128, end)
        values = outcomes[offset:stop]
        scores = values[:, field_indices].sum(axis=2)
        if multiplier != 1.0:
            scores += values[:, field_indices[:, 0]] * (multiplier - 1.0)
        if result is None:
            result = np.lib.format.open_memmap(path, mode="w+", dtype=scores.dtype,
                shape=(end-start, len(field_indices)))
        result[offset-start:stop-start] = np.sort(scores, axis=1)
    if result is None:
        raise ValueError("No evaluation simulations are available")
    result.flush()
    del result
    return owner, np.load(path, mmap_mode="r")


@st.cache_data(show_spinner=False, max_entries=8)
def evaluate_full_roster_portfolio_cached(outcomes, portfolio, field, slots, field_size, tiers, fee, multipliers=None):
    from simmah_contests import evaluate_contest
    return evaluate_contest(outcomes, portfolio, field, slots, field_size, tiers, fee, multipliers=multipliers, joint=True)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_game_weather_json(url):
    """Cache public schedule/forecast responses; failed requests aren't cached."""
    response = requests.get(url, headers={
        "User-Agent": "Simmah-NFL/2.0 (github.com/Meitzlah78/universal-dfs-simulator)",
        "Accept": "application/json",
    }, timeout=(3, 8))
    response.raise_for_status()
    return response.json()


def extract_slate_games(source_df):
    """Return compact matchup labels detected from a DK/FD player table."""
    import re
    if not isinstance(source_df, pd.DataFrame) or source_df.empty:
        return []
    lookup = {str(col).strip().casefold(): col for col in source_df.columns}
    game_col = lookup.get("game info") or lookup.get("gameinfo") or lookup.get("game")
    if game_col is None:
        return []
    games = []
    for raw_value in source_df[game_col].dropna().astype(str):
        value = raw_value.strip().upper()
        match = re.search(r"\b([A-Z]{2,3})\s*@\s*([A-Z]{2,3})\b", value)
        if not match:
            continue
        label = f"{match.group(1)} @ {match.group(2)}"
        if label not in games:
            games.append(label)
    return games




@st.cache_data(show_spinner=False, ttl=300)
def fetch_draftkings_contest_size(contest_id):
    """Best-effort DraftKings contest entry count lookup from the public contest API."""
    contest_id = str(contest_id or "").strip()
    if not contest_id.isdigit():
        return None, None
    url = f"https://api.draftkings.com/contests/v1/contests/{contest_id}?format=json"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=(4, 10))
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None, None

    current_keys = {
        "entries", "entrycount", "entriescount", "currententries",
        "numberofentries", "currententrycount", "contestentrycount",
    }
    max_keys = {
        "maxentries", "maximumentries", "maximumnumberofentries",
        "contestcapacity", "capacity", "totalentries",
    }

    current_values = []
    max_values = []

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = "".join(ch for ch in str(key).casefold() if ch.isalnum())
                if normalized in current_keys:
                    parsed = pd.to_numeric(item, errors="coerce")
                    if pd.notna(parsed) and float(parsed) > 0:
                        current_values.append(int(float(parsed)))
                if normalized in max_keys:
                    parsed = pd.to_numeric(item, errors="coerce")
                    if pd.notna(parsed) and float(parsed) > 0:
                        max_values.append(int(float(parsed)))
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    current_entries = max(current_values) if current_values else None
    max_entries = max(max_values) if max_values else None
    return current_entries, max_entries


def extract_slate_games(source_df):
    """Return compact matchup labels detected from a DK/FD player table."""
    import re
    if not isinstance(source_df, pd.DataFrame) or source_df.empty:
        return []
    lookup = {str(col).strip().casefold(): col for col in source_df.columns}
    game_col = lookup.get("game info") or lookup.get("gameinfo") or lookup.get("game")
    if game_col is None:
        return []
    games = []
    for raw_value in source_df[game_col].dropna().astype(str):
        value = raw_value.strip().upper()
        match = re.search(r"\b([A-Z]{2,3})\s*@\s*([A-Z]{2,3})\b", value)
        if not match:
            continue
        label = f"{match.group(1)} @ {match.group(2)}"
        if label not in games:
            games.append(label)
    return games


@st.cache_data(ttl=300, show_spinner=False)
def automatic_game_lines_cached(games, dates):
    from simmah_auto_game_lines import download_lines
    return download_lines(games, dates)


def show_detected_slate_games(source_df):
    st.session_state["active_game_markets"] = {}
    st.session_state["active_game_lines"] = []
    st.session_state["active_slate_identity"] = ""
    games = extract_slate_games(source_df)
    if not games:
        return
    from simmah_game_lines import implied_scores
    from simmah_weather import team_key
    import hashlib
    # Include the dated source game strings so lines cannot leak to a later slate.
    game_columns = [c for c in source_df if str(c).strip().casefold() in {"game info", "gameinfo", "game"}]
    identity = sorted(set(source_df[game_columns].astype(str).agg("|".join, axis=1)))
    slate_key = hashlib.sha256(repr((platform, lineup_mode, pd.Timestamp.now(tz="America/New_York").date().isoformat(), identity)).encode()).hexdigest()[:16]
    st.write("#### Games on this slate — market-implied scores")
    base = pd.DataFrame({"Game": games, "Game total": [None] * len(games),
                         "Home spread": [None] * len(games)})
    from simmah_rotowire import salary_dates
    dates = tuple(sorted(salary_dates(source_df)))
    if not dates:
        dates = (pd.Timestamp.now(tz="America/New_York").date().isoformat(),)
        st.caption("Salary file is undated: automatic lines match today's games only.")
    try:
        automatic = automatic_game_lines_cached(tuple(games), dates)
        automatic = {game: record for game, record in automatic.items()
                     if pd.Timestamp(record["kickoff"]) > pd.Timestamp.now(tz="UTC")}
    except Exception:
        automatic = {}
        st.caption("Automatic pregame lines unavailable. You can enter verified pregame lines below.")
    with st.expander("Override spreads and totals (optional)", expanded=False):
        st.caption("Leave blank to use automatic lines. Home spread is negative when the home team is favored; 0 means pick’em. Manual values override the corresponding automatic values.")
        lines = st.data_editor(base, disabled=["Game"], hide_index=True,
            column_config={"Game total": st.column_config.NumberColumn(min_value=1., max_value=100., step=.5),
                           "Home spread": st.column_config.NumberColumn(min_value=-50., max_value=50., step=.5)},
            key="game_lines_" + slate_key, use_container_width=True)
    lines = lines.copy()
    sources = {}
    for idx, row in lines.iterrows():
        auto = automatic.get(row["Game"], {})
        manual = False
        for column, field in [("Game total", "total"), ("Home spread", "home_spread")]:
            if pd.isna(row[column]):
                lines.at[idx, column] = auto.get(field)
            else:
                manual = True
        sources[row["Game"]] = "Manual pregame override" if manual else auto.get("source", "Unavailable")
    if automatic:
        fetched = min(record["fetched_at"] for record in automatic.values())
        stamp = pd.Timestamp(fetched).tz_convert("America/New_York").strftime("%I:%M %p ET")
        st.caption(f"Automatic pregame lines: {len(automatic)}/{len(games)} games · fetched {stamp} · cached up to 5 minutes.")
    markets = {}
    for row in lines.to_dict("records"):
        away, home = row["Game"].split(" @ ")
        scores = implied_scores(row["Game total"], row["Home spread"])
        if scores is None:
            st.write(f"**{away} @ {home}** · Implied scores unavailable — enter valid total and spread")
        else:
            away_points, home_points = scores
            markets[team_key(away)] = (away_points, home_points)
            markets[team_key(home)] = (home_points, away_points)
            st.write(f"**{away} {away_points:g} @ {home} {home_points:g}** · Total {float(row['Game total']):g} · {home} {float(row['Home spread']):+g} · {sources[row['Game']]}")
    st.session_state["active_game_markets"] = markets
    st.session_state["active_slate_identity"] = slate_key
    st.session_state["active_game_lines"] = [
        {"matchup": r["Game"], "total": float(r["Game total"]), "home_spread": float(r["Home spread"]),
         "source": sources[r["Game"]], "fetched_at": automatic.get(r["Game"], {}).get("fetched_at")}
        for r in lines.to_dict("records") if implied_scores(r["Game total"], r["Home spread"]) is not None
    ]
    if markets:
        st.caption("Pregame lines populate implied team scores. Experimental field-popularity adjustment (maximum ±15%) applies only without imported ownership. Player projection inputs stay unchanged; new game simulations calibrate team scoring environments to these targets. Run a new build after changing lines.")


@st.cache_data(show_spinner=False, ttl=300)
def fetch_draftkings_contest_size(contest_id):
    """Best-effort DraftKings contest entry count lookup from the public contest API."""
    contest_id = str(contest_id or "").strip()
    if not contest_id.isdigit():
        return None, None
    url = f"https://api.draftkings.com/contests/v1/contests/{contest_id}?format=json"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=(4, 10))
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None, None

    current_keys = {
        "entries", "entrycount", "entriescount", "currententries",
        "numberofentries", "currententrycount", "contestentrycount",
    }
    max_keys = {
        "maxentries", "maximumentries", "maximumnumberofentries",
        "contestcapacity", "capacity", "totalentries",
    }

    current_values = []
    max_values = []

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = "".join(ch for ch in str(key).casefold() if ch.isalnum())
                if normalized in current_keys:
                    parsed = pd.to_numeric(item, errors="coerce")
                    if pd.notna(parsed) and float(parsed) > 0:
                        current_values.append(int(float(parsed)))
                if normalized in max_keys:
                    parsed = pd.to_numeric(item, errors="coerce")
                    if pd.notna(parsed) and float(parsed) > 0:
                        max_values.append(int(float(parsed)))
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    current_entries = max(current_values) if current_values else None
    max_entries = max(max_values) if max_values else None
    return current_entries, max_entries


def get_contest_opponent_target(platform_key, default=MAX_SIMULATED_OPPONENTS):
    """Simulate a representative field capped at a practical size for faster results."""
    contest = st.session_state.get(f"selected_{platform_key}_contest") or {}
    try:
        own_entries = max(0, int(contest.get("your_entries", 0) or 0))
    except (TypeError, ValueError):
        own_entries = 0
    field_size = contest.get("field_size")
    try:
        if field_size is not None and pd.notna(field_size):
            return min(default, max(0, int(float(field_size)) - own_entries))
    except (TypeError, ValueError):
        pass
    return default


def _safe_snapshot_slug(value):
    import re
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_") or "snapshot"


def _pregame_snapshot_dir():
    from pathlib import Path
    folder = Path(__file__).resolve().parent / "data" / "pregame_snapshots"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _postgame_learning_dir():
    from pathlib import Path
    folder = Path(__file__).resolve().parent / "data" / "postgame_learning"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_automatic_pregame_snapshot(snapshot_df, format_label, correlation_pct=0.0, aggressiveness_pct=0.0):
    import hashlib
    import json
    from datetime import datetime

    if not isinstance(snapshot_df, pd.DataFrame) or snapshot_df.empty:
        return None

    now = datetime.now(ZoneInfo("America/New_York"))
    contest_key = "selected_fd_contest" if str(format_label).startswith("FanDuel") else "selected_dk_contest"
    contest = st.session_state.get(contest_key) or {}
    game_date = now.date().isoformat()

    snapshot = snapshot_df.copy()
    from simmah_weather import team_key
    markets = st.session_state.get("active_game_markets", {})
    if "Team" in snapshot:
        values = [markets.get(team_key(t), (np.nan, np.nan)) for t in snapshot["Team"]]
        snapshot["Market Implied Team Points"] = [v[0] for v in values]
        snapshot["Market Implied Opponent Points"] = [v[1] for v in values]
        snapshot["Market Game Total"] = [sum(v) for v in values]
        snapshot["Market Team Spread"] = [v[1] - v[0] for v in values]
    snapshot.insert(0, "GameDate", game_date)
    snapshot.insert(1, "Format", str(format_label))
    snapshot.insert(2, "Snapshot Saved ET", now.strftime("%Y-%m-%d %I:%M:%S %p ET"))
    snapshot["Contest ID"] = str(contest.get("id", "") or "")
    snapshot["Contest Name"] = str(contest.get("name", "") or "")
    snapshot["Entry Fee ($)"] = pd.to_numeric(contest.get("entry_fee"), errors="coerce")
    snapshot["Field Size"] = pd.to_numeric(contest.get("field_size"), errors="coerce")
    snapshot["Your Entries"] = pd.to_numeric(contest.get("your_entries"), errors="coerce")
    snapshot["Game Correlation %"] = round(float(correlation_pct), 1)
    snapshot["Simulation Diversity %"] = round(float(aggressiveness_pct), 1)

    slug = _safe_snapshot_slug(format_label)
    csv_path = _pregame_snapshot_dir() / f"{game_date}_{slug}_latest.csv"
    meta_path = _pregame_snapshot_dir() / f"{game_date}_{slug}_latest.json"
    csv_text = snapshot.to_csv(index=False)
    digest = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    hash_key = f"auto_snapshot_hash_{slug}"

    payout = st.session_state.get("contest_payout_schedule")
    payout_contest_id = str(st.session_state.get("contest_payout_contest_id", "") or "")
    payout_values = (
        np.asarray(payout, dtype=float).tolist()
        if isinstance(payout, np.ndarray)
        and payout_contest_id == str(contest.get("id", "") or "")
        else []
    )
    fee = pd.to_numeric(contest.get("entry_fee"), errors="coerce")
    field_size = pd.to_numeric(contest.get("field_size"), errors="coerce")
    your_entries = pd.to_numeric(contest.get("your_entries"), errors="coerce")
    meta = {
        "game_date": game_date,
        "format": str(format_label),
        "saved_at_et": now.strftime("%Y-%m-%d %I:%M:%S %p ET"),
        "contest_id": str(contest.get("id", "") or ""),
        "contest_name": str(contest.get("name", "") or ""),
        "entry_fee": float(fee) if pd.notna(fee) else None,
        "field_size": int(float(field_size)) if pd.notna(field_size) else None,
        "your_entries": int(float(your_entries)) if pd.notna(your_entries) else None,
        "correlation_pct": float(correlation_pct),
        "aggressiveness_pct": float(aggressiveness_pct),
        "payout_schedule": payout_values,
        "game_lines": st.session_state.get("active_game_lines", []),
        "market_source": "Manual pregame entry" if markets else "Unavailable",
        "slate_id": st.session_state.get("active_slate_identity") or hashlib.sha256(
            snapshot_df[[c for c in ["Name", "Team", "Opponent", "Salary"] if c in snapshot_df]].to_csv(index=False).encode()
        ).hexdigest()[:16],
    }
    if st.session_state.get(hash_key) != digest or not csv_path.exists():
        csv_path.write_text(csv_text, encoding="utf-8")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        st.session_state[hash_key] = digest

    st.session_state["latest_auto_pregame_snapshot"] = snapshot.copy()
    st.session_state["latest_auto_pregame_snapshot_format"] = str(format_label)
    st.session_state["latest_auto_pregame_snapshot_path"] = str(csv_path)
    st.session_state["latest_auto_pregame_snapshot_meta"] = meta
    return csv_path


def save_export_checkpoint(snapshot, metadata, export_data, export_name):
    """Callback receives the exact rendered export and snapshot, before rerun."""
    import copy
    from datetime import datetime, timezone
    from simmah_snapshot_archive import archive_snapshot
    if not isinstance(snapshot, pd.DataFrame) or snapshot.empty:
        st.error("Export snapshot could not be saved: no matching simulation snapshot is available.")
        return
    meta = copy.deepcopy(metadata)
    meta["exported_at_utc"] = datetime.now(timezone.utc).isoformat()
    meta["export_filename"] = export_name
    meta["checkpoint"] = "Lineup export; not confirmation of contest submission or pre-lock timing"
    try:
        path = archive_snapshot(_pregame_snapshot_dir(), snapshot, meta,
            _safe_snapshot_slug(meta.get("format")), meta["slate_id"])
        payload = export_data.encode("utf-8") if isinstance(export_data, str) else bytes(export_data)
        path.with_name(path.stem + "_lineups.csv").write_bytes(payload)
        st.session_state["last_export_snapshot_path"] = str(path)
        st.toast("Export snapshot saved with the exact lineup CSV.")
    except Exception as exc:
        st.error(f"Lineup download is available, but saving its snapshot failed: {exc}")


@st.fragment
def lineup_export_download(*args, **kwargs):
    """Keep export checkpoint callbacks inside a small fragment, not a full app rerun."""
    import copy
    data = kwargs.get("data", args[1] if len(args) > 1 else None)
    name = kwargs.get("file_name", args[2] if len(args) > 2 else "lineups.csv")
    snapshot, metadata = load_latest_automatic_pregame_snapshot(selected_format)
    # Bind copies now: callback execution must not pick up a different slate later.
    kwargs["on_click"] = save_export_checkpoint
    kwargs["args"] = (snapshot.copy(deep=True), copy.deepcopy(metadata), data, name)
    return st.download_button(*args, **kwargs)


def load_latest_automatic_pregame_snapshot(format_label):
    import json

    cached = st.session_state.get("latest_auto_pregame_snapshot")
    if (
        isinstance(cached, pd.DataFrame)
        and not cached.empty
        and st.session_state.get("latest_auto_pregame_snapshot_format") == str(format_label)
    ):
        return cached.copy(), dict(st.session_state.get("latest_auto_pregame_snapshot_meta", {}) or {})

    slug = _safe_snapshot_slug(format_label)
    candidates = sorted(
        _pregame_snapshot_dir().glob(f"*_{slug}_latest.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return pd.DataFrame(), {}
    csv_path = candidates[0]
    try:
        snapshot = pd.read_csv(csv_path)
    except Exception:
        return pd.DataFrame(), {}
    meta_path = csv_path.with_suffix(".json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    except Exception:
        meta = {}
    return snapshot, meta


format_options = {
    "DraftKings Classic": ("DraftKings", "Classic"),
    "DraftKings Showdown": ("DraftKings", "Showdown"),
    "FanDuel Full Roster": ("FanDuel", "Full Roster"),
    "FanDuel Single Game": ("FanDuel", "Single Game"),
    "FanDuel NBA": ("FanDuel", "NBA"),
    "DraftKings NBA": ("DraftKings", "NBA"),
}


def detect_uploaded_dfs_format(uploaded_file):
    """Detect DK/FD and single-game/full-roster from an entries/slate CSV."""
    import csv
    import io

    if uploaded_file is None:
        return None
    try:
        uploaded_file.seek(0)
        raw_text = uploaded_file.getvalue().decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(raw_text)))
        uploaded_file.seek(0)
    except Exception:
        return None
    if not rows:
        return None

    # The first entry-table header is the most reliable place to identify roster type.
    header = [str(cell).strip().upper() for cell in rows[0]]
    header_set = set(header)

    if tuple(header[4:12]) == ("PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"):
        return "DraftKings NBA"

    if tuple(header[4:13]) == ("PG", "SG", "SF", "PF", "C", "G/F", "F/C", "UTIL", "UTIL"):
        return "FanDuel NBA"

    # FanDuel exports use MVP / AnyFLEX wording for single-game and commonly use
    # D rather than DST in full-roster templates.
    is_fd_single = any("MVP" in cell for cell in header) or any("ANYFLEX" in cell for cell in header)
    if is_fd_single:
        return "FanDuel Single Game"

    # DraftKings Showdown entries use CPT plus FLEX slots.
    if "CPT" in header_set:
        return "DraftKings Showdown"

    # Distinguish the full-roster sites using their roster headers and player-table wording.
    all_text = raw_text[:20000].upper()
    if "NICKNAME" in all_text or "FANDUEL" in all_text:
        return "FanDuel Full Roster"
    if "D" in header_set and "DST" not in header_set and "DEF" not in header_set:
        return "FanDuel Full Roster"

    # DK My Contests / lineup templates use DST and the salary table commonly has
    # Name + ID, AvgPointsPerGame, or TeamAbbrev.
    if (
        "DST" in header_set
        or "AVGPOINTSPERGAME" in all_text
        or "TEAMABBREV" in all_text
        or "NAME + ID" in all_text
        or "DRAFTKINGS" in all_text
    ):
        return "DraftKings Classic"

    return None


with _shared_header:
    st.write("### Slate Setup")
    st.caption("Upload your DraftKings or FanDuel entries/slate CSV once. SIMMAH will choose the site and format automatically.")
    auto_slate_file = st.file_uploader(
        "Upload Entries / Slate CSV",
        type=["csv"],
        key="universal_slate_setup_file_"+st.session_state.get("_slate_active",{}).get("id","new")+"_"+str(st.session_state.get("_slate_upload_epoch",0)),
    )

    auto_slate_file = select_upload(st, auto_slate_file)
    if st.session_state.get('_slate_incoming'):
        workspace_stop(st, _loaded_slate_tabs)
    if auto_slate_file is not None:
        detected_format = detect_uploaded_dfs_format(auto_slate_file)
        if detected_format:
            if st.session_state.get("dfs_format") != detected_format:
                st.session_state["dfs_format"] = detected_format
                st.session_state["auto_detected_dfs_format"] = detected_format
                workspace_rerun(st, _loaded_slate_tabs)
            st.success(f"Format detected automatically: {detected_format}")
        else:
            st.error("SIMMAH could not identify this file. Upload the original DraftKings or FanDuel contest entries CSV.")
            workspace_stop(st, _loaded_slate_tabs)

if auto_slate_file is None:
    with _shared_header:
        st.info("Upload an entries/slate CSV to get started.")
    workspace_stop(st, _loaded_slate_tabs)
selected_format = detected_format

if selected_format in {"FanDuel NBA", "DraftKings NBA"}:
    from simmah_nba_import import render_setup as render_nba_setup
    render_nba_setup(st, auto_slate_file, (_tab_contests, _tab_roster, _tab_build, _tab_lineups), _build_controls, game_header=_slate_games_header)
    workspace_stop(st, _loaded_slate_tabs)

# Historical projection accuracy report. This uses pre-game projection snapshots
# matched to actual fantasy points; the volatility check below is not a projection backtest.
with _tab_roster:
    with st.expander("Projection Accuracy Report", expanded=False):
        st.caption(
            "Upload a CSV containing saved pre-game projections and actual fantasy points. "
            "The report measures projection accuracy; it does not judge the simulation distribution."
        )
        accuracy_template = pd.DataFrame(columns=[
            "GameDate", "Name", "Position", "Team", "ProjectionSource",
            "Projection", "ActualPoints"
        ])
        st.download_button(
            "Download Accuracy CSV Template",
            data=accuracy_template.to_csv(index=False).encode("utf-8"),
            file_name="projection_accuracy_template.csv",
            mime="text/csv",
            key="projection_accuracy_template_download",
        )
        accuracy_file = workspace_file_uploader(st,
            "Upload historical projection results CSV",
            type=["csv"],
            key="projection_accuracy_history_upload",
            help=(
                "Required columns: Name, Position, Projection, ActualPoints. "
                "ProjectionSource and GameDate are recommended."
            ),
        )
        if accuracy_file is not None:
            try:
                accuracy_df = pd.read_csv(accuracy_file)
                accuracy_df.columns = [str(c).strip() for c in accuracy_df.columns]
                accuracy_lookup = {str(c).strip().casefold(): c for c in accuracy_df.columns}
                required_accuracy = ["name", "position", "projection", "actualpoints"]
                missing_accuracy = [c for c in required_accuracy if c not in accuracy_lookup]
                if missing_accuracy:
                    st.error(
                        "The uploaded file is missing required columns: "
                        + ", ".join(missing_accuracy)
                        + ". Use the template above and include actual DraftKings points."
                    )
                else:
                    accuracy_df = accuracy_df.rename(columns={
                        accuracy_lookup["name"]: "Name",
                        accuracy_lookup["position"]: "Position",
                        accuracy_lookup["projection"]: "Projection",
                        accuracy_lookup["actualpoints"]: "ActualPoints",
                    })
                    if "ProjectionSource" not in accuracy_df.columns:
                        source_col = accuracy_lookup.get("projectionsource")
                        accuracy_df["ProjectionSource"] = (
                            accuracy_df[source_col] if source_col else "Unknown"
                        )
                    accuracy_df["Projection"] = pd.to_numeric(
                        accuracy_df["Projection"], errors="coerce"
                    )
                    accuracy_df["ActualPoints"] = pd.to_numeric(
                        accuracy_df["ActualPoints"], errors="coerce"
                    )
                    accuracy_df = accuracy_df.dropna(
                        subset=["Name", "Position", "Projection", "ActualPoints"]
                    ).copy()
                    accuracy_df = accuracy_df[
                        np.isfinite(accuracy_df["Projection"])
                        & np.isfinite(accuracy_df["ActualPoints"])
                    ].copy()
                    if accuracy_df.empty:
                        st.warning("No usable projection/actual-point rows were found in that file.")
                    else:
                        accuracy_df["Error"] = accuracy_df["ActualPoints"] - accuracy_df["Projection"]
                        accuracy_df["Absolute Error"] = accuracy_df["Error"].abs()
                        accuracy_df["Squared Error"] = accuracy_df["Error"] ** 2
                        mae = float(accuracy_df["Absolute Error"].mean())
                        rmse = float(np.sqrt(accuracy_df["Squared Error"].mean()))
                        bias = float(accuracy_df["Error"].mean())
                        metric_cols = st.columns(4)
                        metric_cols[0].metric("Player-games", f"{len(accuracy_df):,}")
                        metric_cols[1].metric("MAE", f"{mae:.2f} pts")
                        metric_cols[2].metric("RMSE", f"{rmse:.2f} pts")
                        metric_cols[3].metric("Average bias", f"{bias:+.2f} pts")
                        st.caption("Positive bias means actual scores were higher than projected; negative means projections ran high.")
                        accuracy_df["ProjectionSource"] = (
                            accuracy_df["ProjectionSource"].fillna("Unknown").astype(str)
                        )
                        accuracy_df["Projection band"] = pd.cut(
                            accuracy_df["Projection"],
                            bins=[-np.inf, 5, 10, 15, 20, 25, np.inf],
                            labels=["Under 5", "5–10", "10–15", "15–20", "20–25", "25+"],
                            right=False,
                        )
                        summary_rows = []
                        for group_name, group in [
                            ("By position", accuracy_df.groupby("Position", dropna=False)),
                            ("By source", accuracy_df.groupby("ProjectionSource", dropna=False)),
                            ("By projection range", accuracy_df.groupby("Projection band", dropna=False, observed=False)),
                        ]:
                            summary = group.agg(
                                PlayerGames=("Error", "size"),
                                AverageError=("Error", "mean"),
                                MAE=("Absolute Error", "mean"),
                                MeanSquaredError=("Squared Error", "mean"),
                            ).reset_index()
                            summary["RMSE"] = np.sqrt(summary.pop("MeanSquaredError"))
                            summary.insert(0, "Breakdown", group_name)
                            summary_rows.append(summary.rename(columns={summary.columns[1]: "Group"}))
                        summary_df = pd.concat(summary_rows, ignore_index=True, sort=False)
                        summary_df = summary_df.rename(columns={
                            "AverageError": "Average Bias",
                            "PlayerGames": "Player-Games",
                        })
                        for col in ["Average Bias", "MAE", "RMSE"]:
                            summary_df[col] = pd.to_numeric(summary_df[col], errors="coerce").round(2)
                        st.write("#### Accuracy breakdown")
                        st.dataframe(injury_frame(st, summary_df), use_container_width=True, hide_index=True)
                        st.write("#### Largest projection misses")
                        misses = accuracy_df.sort_values("Absolute Error", ascending=False).head(20)
                        st.dataframe(
                            injury_frame(st, misses[[
                                c for c in [
                                    "GameDate", "Name", "Position", "ProjectionSource",
                                    "Projection", "ActualPoints", "Error", "Absolute Error"
                                ] if c in misses.columns
                            ]].round(2)),
                            use_container_width=True,
                            hide_index=True,
                        )
                        st.download_button(
                            "Download Accuracy Results",
                            data=accuracy_df.to_csv(index=False).encode("utf-8"),
                            file_name="projection_accuracy_results.csv",
                            mime="text/csv",
                            key="projection_accuracy_results_download",
                        )
            except Exception as exc:
                st.error(f"Could not read the projection accuracy file: {exc}")
platform, lineup_mode = format_options[selected_format]
_build_controls.caption(selected_format)
# Render single-game rules before projection/contest loaders can stop the script.
if lineup_mode in {"Showdown", "Single Game"}:
    with _build_controls:
        st.write("### Stack Options")
        render_single_stack_controls(st, platform, lineup_mode)
if st.session_state.pop("refresh_projections_requested", False):
    download_public_projection_table.clear()
    download_rotowire_projections.clear()
    fetch_nfl_injury_statuses.clear()
    fetch_game_weather_json.clear()
    automatic_game_lines_cached.clear()
    # The player-pool load below fetches the selected slate's fresh data.
    # Avoid first downloading a second, untargeted copy for the background check.
    _refresh_throttle_key = "automatic_projection_last_check_" + str(selected_format).strip().casefold().replace(" ", "_")
    st.session_state[_refresh_throttle_key] = _sticky_datetime.now(ZoneInfo("America/New_York"))
    st.session_state["projection_updates_found"] = False
    st.session_state["injury_updates_found"] = False
    st.session_state["shared_projection_updated_at"] = _sticky_datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p %Z")

with _tab_roster:
    automatic_projection_refresh(selected_format)

# Turn the sticky refresh button red whenever new projections or injury updates are detected.
if st.session_state.get("projection_updates_found") or st.session_state.get("injury_updates_found"):
    st.markdown(
        """
        <style>
        .st-key-sticky_projection_bar button {
            background-color: #d62828 !important;
            border-color: #d62828 !important;
            color: #ffffff !important;
        }
        .st-key-sticky_projection_bar button:hover {
            background-color: #b71c1c !important;
            border-color: #b71c1c !important;
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
# Keep the derived values in session state for existing format-specific logic.
st.session_state["dfs_platform"] = platform
st.session_state["lineup_mode_" + platform] = lineup_mode
with _shared_header:
    st.caption("Selected: " + selected_format + " · Contests → Roster & Projections → Build")

# Initialize from the saved slider value; the control itself appears beside SIM.
aggressiveness = float(st.session_state.get(f"lineup_build_aggressiveness_{platform}_{lineup_mode}", 100 if ((platform == "DraftKings" and lineup_mode == "Showdown") or (platform == "FanDuel" and lineup_mode == "Single Game")) else 50)) / 100.0

# The correlation slider is displayed with Build Settings below.
# Read its saved value here; the Build Settings control updates it before SIM runs.
correlation_strength = (
    float(st.session_state.get(f"single_game_correlation_strength_{platform}_{lineup_mode}", 0 if ((platform == "DraftKings" and lineup_mode == "Showdown") or (platform == "FanDuel" and lineup_mode == "Single Game")) else 70)) / 100.0
    if lineup_mode in ("Showdown", "Single Game") else 1.0
)

# SHARED HISTORICAL/PBP PLAYER SIMULATION ENGINE
# ================================
# SETTINGS
# ================================

SIMULATIONS = SIMULATION_COUNT
DISPERSION = 8.0
SALARY_CAP = 50000

# NFL DFS scoring settings. Lineup builders use these site/format rules.
# Player outcomes are still generated from the app's internal estimates; this
# defines the fantasy-point scoring model and the single-game multiplier.
from simmah_nfl_scoring import DFS_SCORING_RULES

def score_nfl_stat_line(stats, platform):
    """Apply the shared, UI-independent NFL scoring rules."""
    from simmah_nfl_scoring import score_nfl_stat_line as shared_score
    return shared_score(stats, platform)


def _simulate_scored_player_outcomes(players_df, platform, rng):
    """Shared DK/FD engine: simulate player outcomes from historical distributions and shared game scripts.

    Projections help set volatility and reasonable upper bounds, but do not force
    simulated averages to equal the supplied projection.
    """
    simulation_progress = st.progress(0, text="Preparing player simulations...")
    historical = load_nfl_historical_player_stats()
    historical_name_index = _build_historical_name_index(historical)
    simulation_progress.progress(0.05, text="Historical data loaded. Preparing game scripts...")
    pbp_status_box = st.empty()
    pbp_status_box.info("Loading NFL play-by-play history...")
    pbp_history = load_nfl_pbp_game_history()
    pbp_status_box.info("Play-by-play history: " + st.session_state.get(
        "nfl_pbp_history_status", "Status not available yet."
    ))
    simulations = {}
    cap_hit_percentages = {}
    n = SIMULATIONS
    correlation_strength = float(
        np.clip(st.session_state.get("active_game_correlation_strength", 1.0), 0.0, 1.0)
    )

    # Prefer actual NFL game totals from play-by-play history. If that download
    # is unavailable, fall back to the existing historical player-week data.
    historical_game_factors = np.array([], dtype=float)
    if not pbp_history.empty and "GamePoints" in pbp_history.columns:
        try:
            valid_games = pbp_history.copy()
            valid_games["GamePoints"] = pd.to_numeric(valid_games["GamePoints"], errors="coerce")
            valid_games = valid_games[valid_games["GamePoints"] > 0]
            score_factors = valid_games["GamePoints"].to_numpy(dtype=float)
            score_center = float(np.median(score_factors)) if len(score_factors) else 0.0
            if len(valid_games) >= 20 and np.isfinite(score_center) and score_center > 0:
                score_factors = score_factors / score_center
                if "GamePlays" in valid_games.columns:
                    play_counts = pd.to_numeric(valid_games["GamePlays"], errors="coerce")
                    play_center = float(play_counts.median())
                    if np.isfinite(play_center) and play_center > 0:
                        pace_factors = play_counts.fillna(play_center).to_numpy(dtype=float) / play_center
                        combined = 0.70 * score_factors + 0.30 * pace_factors
                        historical_game_factors = np.clip(combined, 0.75, 1.25)
                    else:
                        historical_game_factors = np.clip(score_factors, 0.75, 1.25)
                else:
                    historical_game_factors = np.clip(score_factors, 0.75, 1.25)
        except Exception:
            historical_game_factors = np.array([], dtype=float)

    if len(historical_game_factors) < 20 and not historical.empty and "game_id" in historical.columns:
        historical_points_col = next(
            (col for col in ["fantasy_points_ppr", "fantasy_points"] if col in historical.columns),
            None
        )
        if historical_points_col:
            try:
                game_totals = pd.to_numeric(
                    historical[historical_points_col], errors="coerce"
                ).groupby(historical["game_id"]).sum(min_count=1).dropna()
                game_totals = game_totals[game_totals > 0].to_numpy(dtype=float)
                if len(game_totals) >= 20:
                    # Normalize and trim extreme games to keep the historical
                    # factor useful without overwhelming player-level outcomes.
                    center = float(np.median(game_totals))
                    if np.isfinite(center) and center > 0:
                        historical_game_factors = np.clip(
                            game_totals / center, 0.75, 1.25
                        )
            except Exception:
                historical_game_factors = np.array([], dtype=float)

    # Build one shared script per matchup so players in the same game are correlated.
    team_col = "Team" if "Team" in players_df.columns else None
    opponent_col = "Opponent" if "Opponent" in players_df.columns else None
    teams = (
        players_df[team_col].astype(str).str.upper().str.strip().unique().tolist()
        if team_col else []
    )
    team_scripts = {}
    if teams:
        team_opponents = {}
        for team in teams:
            opponent = ""
            if opponent_col:
                rows = players_df[
                    players_df[team_col].astype(str).str.upper().str.strip() == team
                ]
                values = rows[opponent_col].astype(str).str.upper().str.strip()
                values = values[~values.isin(["", "—", "-", "NAN", "NONE"])]
                if not values.empty:
                    opponent = values.iloc[0]
            team_opponents[team] = opponent

        handled = set()
        for team in teams:
            if team in handled:
                continue
            opponent = team_opponents.get(team, "")
            if opponent and opponent in teams and opponent != team:
                # Each simulated game has a shared scoring environment and a
                # random leader. The trailing team tends to pass more; the
                # leading team tends to run more.
                if historical_game_factors.size:
                    # Bootstrap historical game environments for all formats.
                    game_environment = rng.choice(historical_game_factors, size=n, replace=True)
                else:
                    game_environment = np.clip(rng.normal(1.0, 0.12, n), 0.72, 1.30)
                margin = np.abs(rng.normal(0.0, 1.0, n))
                team_a_leads = rng.random(n) < 0.5
                a_leading = np.where(team_a_leads, margin, -margin)
                b_leading = -a_leading
                # Approximate drive/field-position effects alongside turnovers.
                # These are simulated game-environment factors, not a full
                # play-by-play drive engine yet.
                team_giveaways = np.clip(rng.poisson(1.25, n), 0, 4)
                opponent_giveaways = np.clip(rng.poisson(1.25, n), 0, 4)
                team_short_fields = np.clip(rng.binomial(team_giveaways, 0.30), 0, 3)
                opponent_short_fields = np.clip(rng.binomial(opponent_giveaways, 0.30), 0, 3)
                team_red_zone_drives = rng.poisson(2.2, n)
                opponent_red_zone_drives = rng.poisson(2.2, n)
                team_long_field_drives = rng.poisson(2.0, n)
                opponent_long_field_drives = rng.poisson(2.0, n)
                for side, lead_state, giveaways, forced, short_fields, red_zone, long_fields in (
                    (team, a_leading, team_giveaways, opponent_giveaways, team_short_fields, team_red_zone_drives, team_long_field_drives),
                    (opponent, b_leading, opponent_giveaways, team_giveaways, opponent_short_fields, opponent_red_zone_drives, opponent_long_field_drives),
                ):
                    base_scoring = np.clip(game_environment * rng.normal(1.0, 0.07, n), 0.70, 1.35)
                    # Giveaways hurt the offense; short fields help the team
                    # receiving the extra possession. Red-zone drives improve
                    # scoring chances, while long-field drives lower them.
                    turnover_factor = np.clip(1.0 - 0.035 * giveaways, 0.82, 1.0)
                    short_field_factor = np.clip(1.0 + 0.035 * short_fields, 1.0, 1.12)
                    red_zone_factor = np.clip(1.0 + 0.025 * (red_zone - 2.2), 0.90, 1.12)
                    long_field_factor = np.clip(1.0 - 0.018 * (long_fields - 2.0), 0.92, 1.08)
                    team_scripts[side] = {
                        "scoring": np.clip(base_scoring * turnover_factor * short_field_factor * red_zone_factor * long_field_factor, 0.65, 1.42),
                        "leading": lead_state > 0.35,
                        "trailing": lead_state < -0.35,
                        "giveaways": giveaways,
                        "opponent_giveaways": forced,
                        "short_fields": short_fields,
                        "red_zone_drives": red_zone,
                        "long_field_drives": long_fields,
                    }
                handled.add(team)
                handled.add(opponent)
            else:
                # If opponent data is unavailable, retain a modest standalone
                # game environment instead of pretending to know the matchup.
                team_scripts[team] = {
                    "scoring": np.clip(rng.normal(1.0, 0.14, n), 0.70, 1.35),
                    "leading": rng.random(n) < 0.35,
                    "trailing": rng.random(n) < 0.35,
                }

    total_players = max(1, len(players_df))
    for index, (_, row) in enumerate(players_df.iterrows()):
        name = str(row["Name"])
        positions = set(str(row.get("Position", "")).upper().replace(" ", "").split("/"))
        team = str(row.get("Team", "")).upper().strip()
        script = team_scripts.get(team, {
            "scoring": np.ones(n),
            "leading": np.zeros(n, dtype=bool),
            "trailing": np.zeros(n, dtype=bool),
        })

        if "QB" in positions:
            stats = {
                "passing_yards": np.maximum(0, rng.normal(225, 65, n)),
                "passing_tds": rng.poisson(1.45, n),
                "interceptions": rng.poisson(0.65, n),
                "rushing_yards": np.maximum(0, rng.normal(16, 20, n)),
                "rushing_tds": rng.binomial(1, 0.12, n),
                "fumbles_lost": rng.binomial(1, 0.08, n),
            }
            position_type = "QB"
        elif "RB" in positions:
            stats = {
                "rushing_yards": np.maximum(0, rng.normal(55, 30, n)),
                "rushing_tds": rng.binomial(2, 0.18, n),
                "receiving_yards": np.maximum(0, rng.normal(22, 20, n)),
                "receiving_tds": rng.binomial(1, 0.10, n),
                "receptions": rng.poisson(2.5, n),
                "fumbles_lost": rng.binomial(1, 0.04, n),
            }
            position_type = "RB"
        elif "WR" in positions:
            stats = {
                "receiving_yards": np.maximum(0, rng.normal(55, 35, n)),
                "receiving_tds": rng.binomial(1, 0.28, n),
                "receptions": rng.poisson(4.0, n),
                "rushing_yards": np.maximum(0, rng.normal(2, 5, n)),
                "fumbles_lost": rng.binomial(1, 0.02, n),
            }
            position_type = "WR"
        elif "TE" in positions:
            stats = {
                "receiving_yards": np.maximum(0, rng.normal(34, 24, n)),
                "receiving_tds": rng.binomial(1, 0.20, n),
                "receptions": rng.poisson(2.7, n),
                "fumbles_lost": rng.binomial(1, 0.02, n),
            }
            position_type = "TE"
        elif "K" in positions:
            stats = {
                "fg_under_40": rng.poisson(1.0, n),
                "fg_40_49": rng.poisson(0.5, n),
                "fg_50_plus": rng.poisson(0.25, n),
                "extra_points_made": rng.poisson(2.0, n),
            }
            position_type = "K"
        else:
            stats = {
                "sacks": rng.poisson(2.3, n),
                "def_interceptions": rng.binomial(1, 0.7, n),
                "fumble_recoveries": rng.binomial(1, 0.45, n),
                "defensive_tds": rng.binomial(1, 0.08, n),
                "safeties": rng.binomial(1, 0.03, n),
                "blocked_kicks": rng.binomial(1, 0.04, n),
                "points_allowed": np.clip(rng.normal(22, 10, n), 0, 50),
                "yards_allowed": np.clip(rng.normal(350, 80, n), 0, 650),
                "is_defense": 1,
            }
            position_type = "DST"

        scores = np.asarray(score_nfl_stat_line(stats, platform), dtype=float)

        # Historical scores provide the player's own distribution. Do not
        # force the samples to match projections or a salary-based average.
        historical_result = _historical_player_average(
            name, next(iter(positions), ""), platform, historical,
            return_scores=True, historical_name_index=historical_name_index
        )
        has_player_history = historical_result is not None
        historical_anchor_mean = np.nan
        historical_games_used = 0
        if historical_result is not None:
            historical_points, recency_weights = historical_result
            probabilities = recency_weights / recency_weights.sum()
            historical_games_used = int(len(historical_points))
            try:
                historical_anchor_mean = float(np.average(historical_points, weights=probabilities))
            except Exception:
                historical_anchor_mean = float(np.mean(historical_points)) if len(historical_points) else np.nan
            scores = rng.choice(
                historical_points, size=n, replace=True, p=probabilities
            ).astype(float)

        # Anchor sparse/no-history players to a projection-informed distribution.
        # This prevents generic position outcomes from overwhelming tiny projections.
        # Historical player distributions remain unscaled.
        # Anchor the simulated mean to the slate projection and calibrate volatility.
        # Historical results determine the shape, while position-specific limits prevent
        # mismatched or sparse history from creating absurdly wide distributions.
        projection = np.nan
        for projection_column in (
            "Projection", "ProjectedPoints", "FinalProjection",
            "FantasyPoints", "FPTS", "Proj", "Points"
        ):
            if projection_column in row.index:
                candidate = pd.to_numeric(
                    pd.Series([row.get(projection_column)]), errors="coerce"
                ).iloc[0]
                if np.isfinite(candidate) and candidate > 0:
                    projection = float(candidate)
                    break

        # Blend the player's recency-weighted historical fantasy mean directly
        # into the simulation target. This is the missing link that lets core
        # players move away from DFF/DraftEdge when their own NFL history supports it.
        # Keep the source projection as the stronger anchor so old/sparse history
        # cannot overwhelm current role, matchup, or injury information.
        if (
            has_player_history
            and historical_games_used >= 4
            and np.isfinite(historical_anchor_mean)
            and historical_anchor_mean >= 0
            and np.isfinite(projection)
            and projection > 0
        ):
            _historical_gap = historical_anchor_mean - projection
            # More history earns slightly more influence. Typical weight is 18-28%.
            _history_weight = float(np.clip(0.14 + 0.012 * historical_games_used, 0.18, 0.28))
            _history_points = _historical_gap * _history_weight
            # Core players may move more than fringe players, but no historical
            # signal alone can create an unsupported multi-point jump.
            _history_cap = float(np.clip(0.30 + projection * 0.065, 0.45, 1.35))
            _history_points = float(np.clip(_history_points, -_history_cap, _history_cap))
            projection = max(0.01, projection + _history_points)

        # Let the simulation mean move away from DFF/DraftEdge when slate context
        # gives us a real reason. The source projection remains the anchor, while
        # historical/PBP outcomes still determine the shape and volatility.
        if np.isfinite(projection) and projection > 0:
            try:
                _team = str(row.get("Team", "")).strip().upper()
                _opp = str(row.get("Opponent", "")).strip().upper()
                _pos = str(row.get("Position", "")).strip().upper().replace(" ", "")
                _injury = str(row.get("Injury Status", row.get("Status", ""))).strip().casefold()

                _pool_context = players_df.copy()
                _pool_context["_ctx_projection"] = pd.to_numeric(
                    _pool_context.get("Projection", 0), errors="coerce"
                ).fillna(0.0)
                _pool_context["_ctx_team"] = _pool_context.get("Team", "").astype(str).str.strip().str.upper()
                _team_totals = _pool_context.groupby("_ctx_team")["_ctx_projection"].sum()
                _positive_team_totals = _team_totals[_team_totals > 0]
                _median_team_total = float(_positive_team_totals.median()) if len(_positive_team_totals) else 0.0
                _team_total = float(_team_totals.get(_team, 0.0))
                _opp_total = float(_team_totals.get(_opp, 0.0)) if _opp else 0.0

                # Environment signal: scale projected game strength into a direct
                # point adjustment instead of only a tiny percentage change.
                _environment_points = 0.0
                if _median_team_total > 0 and (_team_total > 0 or _opp_total > 0):
                    _game_team_average = np.mean([v for v in (_team_total, _opp_total) if v > 0])
                    _environment_points = float(np.clip(
                        (_game_team_average / _median_team_total - 1.0) * 3.0,
                        -0.75,
                        0.75,
                    ))

                # Role signal: concentrated skill-player roles get a direct bump,
                # while thin roles get a small reduction. This creates meaningful
                # movement even for mid-range projections.
                _role_points = 0.0
                if _team_total > 0 and _pos.split("/")[0] in {"RB", "WR", "TE"}:
                    _share = projection / _team_total
                    if _share >= 0.30:
                        _role_points = 0.90
                    elif _share >= 0.24:
                        _role_points = 0.60
                    elif _share >= 0.18:
                        _role_points = 0.30
                    elif _share <= 0.05:
                        _role_points = -0.45
                    elif _share <= 0.09:
                        _role_points = -0.25

                _injury_points = -0.35 if "question" in _injury else 0.0

                # Scale the allowed movement with player importance. Cheap fringe
                # players should not move as much as core plays. Hard cap remains.
                _importance_cap = float(np.clip(0.35 + projection * 0.055, 0.50, 1.50))
                _context_points = float(np.clip(
                    _environment_points + _role_points + _injury_points,
                    -_importance_cap,
                    _importance_cap,
                ))
                projection = max(0.01, projection + _context_points)
            except Exception:
                # Never break a slate because one row is missing context fields.
                pass

        # Position-specific volatility targets. Historical data still informs
        # each player's spread, but blending it with a position baseline helps
        # prevent noisy samples from creating extreme tails.
        position_cv_limits = {
            "QB": (0.25, 0.55, 0.40),
            "RB": (0.25, 0.60, 0.45),
            "WR": (0.30, 0.60, 0.50),
            "TE": (0.30, 0.60, 0.50),
            "K": (0.20, 0.40, 0.30),
            "DST": (0.35, 0.65, 0.50),
        }
        min_cv, max_cv, baseline_cv = position_cv_limits.get(
            position_type, (0.30, 0.55, 0.45)
        )
        sampled_mean = float(np.mean(scores)) if len(scores) else 0.0
        sampled_std = float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0
        if position_type == "K" and np.isfinite(projection) and projection > 0:
            # Kicker historical samples may be all-zero or mismatched. If
            # usable, retain their shape while scaling toward the projection;
            # otherwise generate a projection-centered distribution.
            if np.isfinite(sampled_mean) and sampled_mean > 1e-6:
                scores = np.maximum(
                    0.0,
                    scores * (projection / sampled_mean)
                    + rng.normal(0.0, max(0.25, projection * 0.12), size=n),
                )
            else:
                scores = np.maximum(
                    0.0,
                    rng.normal(projection, max(1.0, projection * 0.30), size=n),
                )
            sampled_mean = float(np.mean(scores))
            sampled_std = float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0
        elif (
            not has_player_history
            and np.isfinite(projection) and projection > 0
            and np.isfinite(sampled_mean) and sampled_mean > 1e-6
        ):
            scores = np.maximum(
                0.0,
                scores * (projection / sampled_mean)
                + rng.normal(0.0, max(0.25, projection * 0.20), size=n),
            )
            sampled_mean = float(np.mean(scores))
            sampled_std = float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0

        if np.isfinite(projection) and projection > 0:
            # Use half historical volatility and half position baseline, then
            # cap the result to reduce over-wide P90/P95/P99 outcomes.
            if sampled_mean > 0 and np.isfinite(sampled_std) and sampled_std > 0:
                historical_cv = sampled_std / sampled_mean
                blended_cv = 0.50 * historical_cv + 0.50 * baseline_cv
                volatility_cv = float(np.clip(blended_cv, min_cv, max_cv))
            else:
                volatility_cv = baseline_cv
            target_std = max(0.5, projection * volatility_cv)

            if sampled_std > 1e-6 and np.isfinite(sampled_std):
                # Limit extreme historical outliers before rescaling. This reduces
                # unrealistic P95/P99 values while retaining player-specific shape.
                standardized = (scores - sampled_mean) / sampled_std
                standardized = np.clip(standardized, -3.0, 3.0)
                standardized_mean = float(np.mean(standardized))
                standardized_std = float(np.std(standardized, ddof=1))
                if standardized_std > 1e-6 and np.isfinite(standardized_std):
                    standardized = (
                        (standardized - standardized_mean)
                        * (target_std / standardized_std)
                    )
                    # Center on the blended target mean. The target already
                    # includes recency-weighted player history plus slate context,
                    # so we keep the historical shape without snapping back to raw DFF.
                    scores = projection + standardized
                    # Historical weekly scores are discrete, so repeated sampled values can
                    # make P90/P95/P99 collapse to the exact same number. Add a very small
                    # mean-zero smoothing term only to historical samples. This separates
                    # percentile ties without materially changing the player's mean or spread.
                    if has_player_history:
                        _tie_smoothing_std = max(0.05, target_std * 0.04)
                        _tie_noise = rng.normal(0.0, _tie_smoothing_std, size=n)
                        _tie_noise = _tie_noise - float(np.mean(_tie_noise))
                        scores = scores + _tie_noise
                else:
                    # Sparse/constant historical samples can have a nonzero
                    # raw spread but no usable spread after outlier trimming.
                    # Generate a distribution rather than a flat line.
                    scores = rng.normal(max(0.0, projection), target_std, size=n)
            else:
                # If the sampled history has no usable spread, retain its own
                # average and use the projection only to set the spread.
                scores = rng.normal(max(0.0, projection), target_std, size=n)

            # Fantasy scores cannot be negative.
            scores = np.maximum(scores, 0.0)

            # Low-projection players often have sparse or discrete history,
            # which can leave several displayed percentiles identical. Use a
            # positive, right-skewed distribution for these players so they
            # retain a realistic chance of zero while keeping the mean anchored
            # to the supplied projection.
            if projection <= 3.0:
                low_projection_cv = max(volatility_cv, 0.45)
                gamma_shape = 1.0 / (low_projection_cv ** 2)
                scores = rng.gamma(
                    shape=gamma_shape,
                    scale=max(projection, 0.01) / gamma_shape,
                    size=n,
                )
        # Shared game script adjusts the sampled outcome modestly. Trailing teams
        # throw more; leading teams lean more on their running backs.
        # Scale shared game-script effects with the user's single-game slider.
        # At 0%, players still have their own outcome variation, but shared
        # scoring/lead-trail adjustments are neutralized.
        raw_scoring_factor = script["scoring"]
        scoring_factor = 1.0 + (raw_scoring_factor - 1.0) * correlation_strength
        trailing = script["trailing"].astype(float) * correlation_strength
        leading = script["leading"].astype(float) * correlation_strength
        if position_type in ("QB", "WR", "TE"):
            script_factor = scoring_factor + trailing * 0.12 - leading * 0.06
        elif position_type == "RB":
            script_factor = scoring_factor + leading * 0.10 - trailing * 0.08
        elif position_type == "DST":
            script_factor = 2.0 - scoring_factor
        else:
            script_factor = scoring_factor

        script_factor = np.clip(script_factor, 0.80, 1.20)
        final_scores = np.maximum(scores * script_factor, 0.0)
        # Defensive turnover points are already represented in the sampled
        # defensive outcomes. Do not add opponent giveaways a second time.
        # Limit extreme simulated outcomes without shifting the distribution
        # back to the projection. The projection sets a reasonable ceiling, but
        # historical results and game scripts determine the simulated average.
        if np.isfinite(projection) and projection > 0:
            upper_cap = max(1.0, projection * (1.0 + 3.0 * volatility_cv))
            final_scores = np.minimum(final_scores, upper_cap)
            cap_tolerance = max(0.01, upper_cap * 1e-6)
            cap_hit_percentages[name] = round(
                100.0 * float(np.mean(final_scores >= upper_cap - cap_tolerance)), 2
            )
        simulations[name] = final_scores
        if index == 0 or (index + 1) % 2 == 0 or index + 1 == total_players:
            progress_value = 0.05 + 0.90 * (index + 1) / total_players
            simulation_progress.progress(
                min(0.95, progress_value),
                text=f"Simulating players: {index + 1} of {total_players} ({(index + 1) / total_players:.0%})"
            )

    result = pd.DataFrame(simulations)
    st.session_state["simulation_cap_hit_pct"] = cap_hit_percentages
    simulation_progress.progress(1.0, text=f"Player simulations complete: {total_players} players")

    return result

@st.cache_data(show_spinner=False, ttl=86400)
def _download_nfl_historical_player_stats():
    """Download historical NFL stats once per cache period, with a network timeout."""
    import io
    import requests

    frames = []
    loaded_seasons = []
    errors = []
    # Load the current season plus recent seasons for player history.
    # The 2026 file may not be published yet; failures are recorded and older
    # seasons still load. Streamlit caches the result for 24 hours.
    # Short per-request timeouts ensure unavailable data falls back promptly.
    for season in [2026, 2025, 2024, 2023]:
        url = f"https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
        try:
            response = requests.get(url, timeout=(4, 10))
            response.raise_for_status()
            frame = pd.read_csv(io.BytesIO(response.content), low_memory=False)
            if not frame.empty:
                frame["season"] = season
                frames.append(frame)
                loaded_seasons.append(season)
        except Exception as exc:
            errors.append(f"{season}: {str(exc)[:120]}")
    historical = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return historical, loaded_seasons, errors


def load_nfl_historical_player_stats():
    """Use Streamlit's shared cache so reruns reuse data instead of downloading it again."""
    try:
        historical, loaded_seasons, errors = _download_nfl_historical_player_stats()
    except Exception as exc:
        historical, loaded_seasons, errors = pd.DataFrame(), [], [str(exc)]
    if loaded_seasons:
        st.session_state["nfl_historical_stats_status"] = (
            "Historical NFL data cached for reuse. Loaded seasons: "
            + ", ".join(str(year) for year in loaded_seasons)
            + ". Cache refreshes every 24 hours."
        )
    else:
        detail = (" " + "; ".join(errors[:2])) if errors else ""
        st.session_state["nfl_historical_stats_status"] = (
            "Historical NFL data could not be downloaded; using salary/position estimates."
            + detail
        )
    return historical


@st.cache_data(show_spinner=False, ttl=86400)
def _download_nfl_pbp_game_history():
    """Load archived repo PBP first, then fill missing history from nflverse."""
    from pathlib import Path
    import requests

    wanted_columns = {
        "season", "week", "game_id", "play_id", "play_type", "total_home_score",
        "total_away_score", "game_seconds_remaining", "qtr"
    }
    required = {"game_id", "total_home_score", "total_away_score"}
    local_frames = []
    remote_frames = []
    local_archives = []
    loaded_seasons = []
    errors = []

    def summarize_pbp(frame, season_hint=None):
        if frame is None or frame.empty or not required.issubset(frame.columns):
            return pd.DataFrame()
        work = frame.copy()
        if "season" not in work.columns:
            work["season"] = season_hint
        elif season_hint is not None:
            work["season"] = pd.to_numeric(work["season"], errors="coerce").fillna(season_hint)
        work["_play_order"] = pd.to_numeric(
            work.get("play_id", pd.Series(np.arange(len(work)), index=work.index)), errors="coerce"
        )
        work["_home_score"] = pd.to_numeric(work["total_home_score"], errors="coerce")
        work["_away_score"] = pd.to_numeric(work["total_away_score"], errors="coerce")
        if "play_id" not in work.columns:
            work["play_id"] = np.nan
        if "play_type" not in work.columns:
            work["play_type"] = ""
        work = work.dropna(subset=["game_id", "_home_score", "_away_score"])
        if work.empty:
            return pd.DataFrame()
        final_scores = (
            work.sort_values("_play_order")
            .groupby("game_id", sort=False)
            .tail(1)
            .copy()
        )
        final_scores["GamePoints"] = final_scores["_home_score"] + final_scores["_away_score"]
        play_counts = work.groupby("game_id").agg(
            GamePlays=("play_id", "count"),
            PassPlays=("play_type", lambda values: values.astype(str).str.lower().eq("pass").sum()),
            RunPlays=("play_type", lambda values: values.astype(str).str.lower().eq("run").sum()),
        ).reset_index()
        final_scores = final_scores.merge(play_counts, on="game_id", how="left")
        final_scores[["GamePlays", "PassPlays", "RunPlays"]] = (
            final_scores[["GamePlays", "PassPlays", "RunPlays"]].fillna(0)
        )
        final_scores["season"] = pd.to_numeric(final_scores["season"], errors="coerce")
        return final_scores[
            ["season", "game_id", "GamePoints", "GamePlays", "PassPlays", "RunPlays"]
        ]

    # 1) Repo archives are the durable source of truth for completed weeks.
    archive_dir = Path("data/pbp")
    if archive_dir.exists():
        for archive_path in sorted(archive_dir.glob("*.csv.gz")):
            try:
                season_match = re.match(r"(\d{4})_week_(\d{2})\.csv\.gz$", archive_path.name)
                season_hint = int(season_match.group(1)) if season_match else None
                frame = pd.read_csv(
                    archive_path,
                    usecols=lambda column: column in wanted_columns,
                    low_memory=False,
                )
                summarized = summarize_pbp(frame, season_hint=season_hint)
                if not summarized.empty:
                    local_frames.append(summarized)
                    local_archives.append(archive_path.name)
                    for season_value in summarized["season"].dropna().astype(int).unique():
                        loaded_seasons.append(int(season_value))
            except Exception as exc:
                errors.append(f"{archive_path.name}: {str(exc)[:120]}")

    # 2) nflverse fills older/missing history. Local archived game_ids win on duplicates.
    for season in range(2020, 2027):
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv"
        try:
            with requests.get(url, timeout=(10, 60), stream=True) as response:
                response.raise_for_status()
                response.raw.decode_content = True
                frame = pd.read_csv(
                    response.raw,
                    usecols=lambda column: column in wanted_columns,
                    low_memory=False,
                )
            summarized = summarize_pbp(frame, season_hint=season)
            if summarized.empty:
                errors.append(f"{season}: play-by-play file did not contain required score columns")
                continue
            remote_frames.append(summarized)
            loaded_seasons.append(season)
        except Exception as exc:
            errors.append(f"{season}: {str(exc)[:120]}")

    frames = local_frames + remote_frames
    history = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["season", "game_id", "GamePoints", "GamePlays", "PassPlays", "RunPlays"]
    )
    if not history.empty:
        # Local archive rows were concatenated first, so keep='first' gives them priority.
        history = history.drop_duplicates(subset=["game_id"], keep="first").reset_index(drop=True)
    return history, sorted(set(loaded_seasons)), errors, local_archives


def load_nfl_pbp_game_history():
    """Return cached PBP history, preferring the repo's saved weekly archives."""
    try:
        history, loaded_seasons, errors, local_archives = _download_nfl_pbp_game_history()
    except Exception as exc:
        history, loaded_seasons, errors, local_archives = pd.DataFrame(), [], [str(exc)[:120]], []

    if loaded_seasons:
        archive_text = (
            f" Repo archives loaded first: {len(local_archives)} file(s)"
            + (f" ({', '.join(local_archives[-3:])})" if local_archives else "")
            + "."
        ) if local_archives else " No repo PBP archive was found; nflverse was used."
        st.session_state["nfl_pbp_history_status"] = (
            "Play-by-play game history loaded for seasons "
            + ", ".join(str(year) for year in loaded_seasons)
            + "."
            + archive_text
            + " nflverse fills missing history. Cached for 24 hours."
        )
    else:
        st.session_state["nfl_pbp_history_status"] = (
            "Play-by-play history unavailable; using historical player stats instead."
            + ((" " + "; ".join(errors[:2])) if errors else "")
        )
    return history


def build_historical_volatility_check(historical):
    """Compare observed weekly score variation with the simulator's position CV targets."""
    if historical is None or historical.empty or "position" not in historical.columns:
        return pd.DataFrame()

    score_col = next(
        (col for col in ["fantasy_points", "fantasy_points_ppr"] if col in historical.columns),
        None,
    )
    name_col = next(
        (col for col in ["player_id", "player_display_name", "player_name", "name"] if col in historical.columns),
        None,
    )
    if not score_col or not name_col or "week" not in historical.columns:
        return pd.DataFrame()

    data = historical.copy()
    data["_score"] = pd.to_numeric(data[score_col], errors="coerce")
    data["_week"] = pd.to_numeric(data["week"], errors="coerce")
    data["_position"] = data["position"].astype(str).str.upper().str.strip()
    data = data[
        data["_position"].isin(["QB", "RB", "WR", "TE", "K", "DST"])
        & data["_week"].between(1, 18)
        & data["_score"].notna()
    ].copy()
    if data.empty:
        return pd.DataFrame()

    # One score per player per season/week; use player IDs when available.
    dedupe = [c for c in ["season", name_col, "_week"] if c in data.columns]
    if dedupe:
        data = data.drop_duplicates(subset=dedupe, keep="last")
    player_key = (data["season"].astype(str) + ":" if "season" in data.columns else "") + data[name_col].astype(str)
    data["_player_key"] = player_key
    player_rows = []
    for (position, player), group in data.groupby(["_position", "_player_key"], sort=False):
        scores = group["_score"].astype(float)
        if len(scores) < 8 or scores.mean() < 5.0:
            continue
        mean_score = float(scores.mean())
        if mean_score <= 0:
            continue
        player_rows.append({
            "Position": position,
            "Games": len(scores),
            "Historical Mean": mean_score,
            "Historical CV %": 100.0 * float(scores.std(ddof=1)) / mean_score,
        })
    per_player = pd.DataFrame(player_rows)
    if per_player.empty:
        return pd.DataFrame()

    targets = {"QB": 40, "RB": 45, "WR": 50, "TE": 50, "K": 30, "DST": 50}
    rows = []
    for position, group in per_player.groupby("Position"):
        observed = float(group["Historical CV %"].median())
        target = targets.get(position, 45)
        rows.append({
            "Position": position,
            "Players Tested": len(group),
            "Median Historical CV %": round(observed, 1),
            "Current Simulator Target CV %": target,
            "Difference (points)": round(target - observed, 1),
            "Initial Read": (
                "Target may be too wide" if target - observed >= 10
                else "Target may be too narrow" if target - observed <= -10
                else "Roughly in range"
            ),
        })
    return pd.DataFrame(rows).sort_values("Position").reset_index(drop=True)


def _normalize_historical_player_names(values):
    """Normalize player names once so historical matching does not rescan all rows per player."""
    return (
        values.astype(str)
        .str.casefold()
        .str.replace(r"[^a-z0-9 ]", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def _build_historical_name_index(historical):
    """Build a reusable name-to-rows index for one simulation run."""
    if historical.empty:
        return {}
    name_col = next((col for col in ["player_display_name", "player_name", "name"] if col in historical.columns), None)
    if name_col is None or "week" not in historical.columns:
        return {}
    prepared = historical.copy()
    prepared["_normalized_player_name"] = _normalize_historical_player_names(prepared[name_col])
    return {
        name: group.drop(columns=["_normalized_player_name"])
        for name, group in prepared.groupby("_normalized_player_name", sort=False)
        if name
    }


def _historical_player_average(player_name, position, platform, historical, return_scores=False, historical_name_index=None):
    """Return recency-weighted fantasy points, or the recent weekly scores themselves."""
    if historical.empty:
        return None
    name_col = next((col for col in ["player_display_name", "player_name", "name"] if col in historical.columns), None)
    if name_col is None or "week" not in historical.columns:
        return None
    wanted = " ".join(str(player_name).casefold().replace(".", "").replace(",", "").split())
    wanted = " ".join(pd.Series([wanted]).str.replace(r"[^a-z0-9 ]", "", regex=True).iloc[0].split())
    if historical_name_index is not None:
        rows = historical_name_index.get(wanted)
        if rows is None:
            return None
        rows = rows.copy()
    else:
        names = _normalize_historical_player_names(historical[name_col])
        rows = historical[names == wanted].copy()
    if rows.empty:
        return None
    # Use regular-season records only when the source identifies game type.
    # Playoff and preseason usage can differ substantially from normal weekly roles.
    if "season_type" in rows.columns:
        season_type = rows["season_type"].astype(str).str.strip().str.upper()
        rows = rows[season_type.isin(["REG", "REGULAR", "REGULAR_SEASON"])].copy()
    if rows.empty:
        return None

    # Do not silently use records from another position when a position match
    # is available in the source. Ambiguous or mismatched history is safer to skip.
    if "position" in rows.columns and position:
        matching = rows[rows["position"].astype(str).str.upper().str.strip() == str(position).upper().strip()]
        if matching.empty:
            return None
        rows = matching.copy()

    if "season" in rows.columns:
        rows["season"] = pd.to_numeric(rows["season"], errors="coerce")
    else:
        rows["season"] = 0
    rows["week"] = pd.to_numeric(rows["week"], errors="coerce")
    rows = rows[rows["week"].between(1, 18, inclusive="both")].copy()
    rows = rows.dropna(subset=["week"])
    if rows.empty:
        return None

    # If the same normalized name maps to multiple NFL player IDs at the same
    # position, do not blend those players' histories together. A bad match is
    # worse than falling back to the model's projection-based distribution.
    if "player_id" in rows.columns:
        ids = rows["player_id"].dropna().astype(str).str.strip()
        ids = ids[ids.ne("")]
        if ids.nunique() > 1:
            return None

    # A player should contribute at most one record per game. Remove duplicate
    # player/game rows if the source contains them. Keep a longer recent window
    # now that three seasons are available.
    dedupe_cols = [col for col in ["player_id", "game_id"] if col in rows.columns]
    if len(dedupe_cols) == 2:
        rows = rows.drop_duplicates(subset=dedupe_cols, keep="last")
    elif "game_id" in rows.columns:
        rows = rows.drop_duplicates(subset=["game_id"], keep="last")

    rows = rows.sort_values(["season", "week"]).tail(30)
    if rows.empty:
        return None
    if str(platform).lower().startswith("fanduel"):
        stats_map = {
            "passing_yards": "passing_yards", "passing_tds": "passing_tds",
            "interceptions": "interceptions", "rushing_yards": "rushing_yards",
            "rushing_tds": "rushing_tds", "receiving_yards": "receiving_yards",
            "receiving_tds": "receiving_tds", "receptions": "receptions",
        }
        scores = []
        for _, game in rows.iterrows():
            stat_line = {}
            for output_col, source_col in stats_map.items():
                if source_col in rows.columns:
                    stat_line[output_col] = pd.to_numeric(pd.Series([game[source_col]]), errors="coerce").fillna(0).iloc[0]
            for output, candidates in {
                "fumbles_lost": ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"),
                "two_point_conversions": ("passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions"),
            }.items():
                stat_line[output] = sum(
                    float(pd.to_numeric(pd.Series([game.get(col, 0)]), errors="coerce").fillna(0).iloc[0])
                    for col in candidates
                )
            scores.append(float(score_nfl_stat_line(stat_line, platform)))
        points = np.asarray(scores, dtype=float)
    else:
        points_col = next((col for col in ["fantasy_points_ppr", "fantasy_points"] if col in rows.columns), None)
        if points_col is None:
            return None
        points = pd.to_numeric(rows[points_col], errors="coerce").fillna(0).to_numpy(dtype=float)
    weights = np.linspace(0.5, 1.5, len(points))
    # Gently favor games that match the player's current workload. This
    # changes sampling frequency, not the underlying scoring or projections.
    # Keep the adjustment bounded so a single high-usage game cannot dominate.
    usage_columns = []
    normalized_position = str(position or "").upper().strip()
    if normalized_position == "QB":
        usage_columns = [col for col in ["attempts", "carries"] if col in rows.columns]
    elif normalized_position == "RB":
        usage_columns = [col for col in ["carries", "targets"] if col in rows.columns]
    elif normalized_position in {"WR", "TE"}:
        usage_columns = [col for col in ["targets"] if col in rows.columns]
        if not usage_columns and "receptions" in rows.columns:
            usage_columns = ["receptions"]
    if usage_columns and len(points) == len(rows) and len(points) >= 4:
        usage_parts = []
        for col in usage_columns:
            values = pd.to_numeric(rows[col], errors="coerce").fillna(0).clip(lower=0).to_numpy(dtype=float)
            # Targets are a useful role signal but slightly less direct than
            # carries/attempts, so scale them to avoid overwhelming the measure.
            usage_parts.append(values * (1.25 if col == "targets" and normalized_position == "RB" else 1.0))
        workload = np.sum(np.vstack(usage_parts), axis=0)
        positive_workload = workload[workload > 0]
        if len(positive_workload) >= 3:
            reference = float(np.median(positive_workload))
            if np.isfinite(reference) and reference > 0:
                usage_multiplier = np.clip(workload / reference, 0.75, 1.25)
                # Blend with neutral weighting to limit impact from role changes
                # and noisy weekly stats.
                weights = weights * (0.5 + 0.5 * usage_multiplier)
    average = float(np.average(points, weights=weights))
    if return_scores:
        return (points, weights) if len(points) and np.isfinite(points).all() else None
    return max(0.0, average) if np.isfinite(average) else None

def build_internal_projection_means(players_df, platform="DraftKings", include_history=False):
    """Blend salary/position estimates with recency-weighted historical NFL results."""
    salary = pd.to_numeric(players_df["Salary"], errors="coerce").fillna(0).to_numpy(dtype=float)
    positions = players_df["Position"].astype(str).str.upper().str.split("/")
    position_rates = {
        "QB": 2.00, "RB": 1.75, "WR": 1.70, "TE": 1.50,
        "K": 1.35, "DST": 1.35, "D": 1.35, "DEF": 1.35,
    }
    baseline = []
    for pay, eligible_positions in zip(salary, positions):
        rates = [position_rates[pos.strip()] for pos in eligible_positions if pos.strip() in position_rates]
        rate = max(rates) if rates else 1.60
        baseline.append(max(0.3, (pay / 1000.0) * rate))
    baseline = np.asarray(baseline, dtype=float)
    # Avoid network downloads while the app page is starting up. Load historical data only when a simulation is explicitly run.
    historical = load_nfl_historical_player_stats() if include_history else pd.DataFrame()
    blended = []
    matched = 0
    for index, (_, row) in enumerate(players_df.iterrows()):
        pos = str(row.get("Position", "")).upper().split("/")[0].strip()
        historical_avg = _historical_player_average(row.get("Name", ""), pos, platform, historical)
        if historical_avg is None:
            blended.append(baseline[index])
        else:
            # Historical performance is informative, but salary-based opportunity
            # prevents tiny samples from overpowering the estimate.
            blended.append(max(0.3, 0.65 * historical_avg + 0.35 * baseline[index]))
            matched += 1
    st.session_state["nfl_historical_players_matched"] = matched
    return np.asarray(blended, dtype=float)


def fetch_fanduel_contest_details(contest_id):
    """Best-effort public FanDuel contest lookup. Never requires user credentials."""
    contest_id = str(contest_id or "").strip()
    if not contest_id:
        return None
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    }
    urls = [
        f"https://api.fanduel.com/contests/{contest_id}",
        f"https://api.fanduel.com/contests?contest={contest_id}",
        f"https://api.fanduel.com/contests?id={contest_id}",
    ]
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code != 200:
                continue
            payload = response.json()
            candidates = []
            if isinstance(payload, dict):
                if isinstance(payload.get("contests"), list):
                    candidates.extend(payload["contests"])
                candidates.append(payload)
            elif isinstance(payload, list):
                candidates.extend(payload)
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id", item.get("contest_id", ""))).strip()
                if item_id and item_id != contest_id:
                    continue
                size = item.get("size", {}) if isinstance(item.get("size"), dict) else {}
                prizes = item.get("prizes", {}) if isinstance(item.get("prizes"), dict) else {}
                details = {
                    "field_size": item.get("max_size") or size.get("max") or item.get("size_max"),
                    "current_entries": item.get("entry_count") or item.get("entries_count") or item.get("open_count"),
                    "max_entries_per_user": item.get("max_entries_per_user"),
                    "prize_pool": prizes.get("total") or item.get("prize_pool") or item.get("prize_total"),
                    "prize_summary": prizes.get("summary") or item.get("prize_summary"),
                    "raw": item,
                }
                if any(details.get(k) not in (None, "", 0) for k in ("field_size", "current_entries", "max_entries_per_user", "prize_pool", "prize_summary")):
                    return details
        except Exception:
            continue
    return None



def render_saved_market_calibration(platform_name, mode_name, pool):
    metadata = st.session_state.get("simulation_preparation_" + platform_name, {})
    rows = metadata.get("market_report", [])
    saved_names = {str(row.get("Name", "")) for row in metadata.get("input_players", [])}
    if not rows or saved_names != set(pool["Name"].astype(str)):
        return
    with st.expander("Market scoring calibration — last completed simulation", expanded=True):
        st.caption("Market target is the implied team score from the spread and total. Pilot mean is the scoring average after calibration; it need not match exactly.")
        report = pd.DataFrame(rows)
        st.dataframe(report, hide_index=True, use_container_width=True)
        st.download_button("DOWNLOAD MARKET CALIBRATION", report.to_csv(index=False).encode("utf-8"),
            "Simmah_Market_Calibration.csv", "text/csv", key="market_calibration_" + platform_name + mode_name,
            on_click="ignore")


def build_joint_candidate_pool(pool, platform_name, mode_name, evaluation_outcomes, roster,
                              salary_min, salary_max, locks=(), selected_stacks=(), secondary_stacks=(), special_allowed=None,
                              salary_costs=None, aggressiveness=.5):
    from simmah_candidates import build_candidates, summarize_candidates, offense_vs_defense_allowed
    # Separate random game draws keep candidate construction out of the contest
    # evaluation sample. Neither matrix is resampled from the other.
    from simmah_simulation_store import construction_for_build
    if len(evaluation_outcomes) != SIMULATION_COUNT:
        raise ValueError("Run SIM: the evaluation matrix does not contain the required outcome count")
    st.info("Loading prepared construction outcomes; BUILD does not rerun the football simulator.")
    construction = construction_for_build(evaluation_outcomes, pool, platform_name, simulation_cache_root(),
        count=SIMULATION_COUNT, market_targets=st.session_state.get("active_game_markets", {}),
        correlation_strength=(1.0 if mode_name in {"Classic", "Full Roster"} else
            float(st.session_state.get("active_game_correlation_strength", 0.0))))
    multipliers = [1.5, 1, 1, 1, 1, 1] if mode_name in {"Showdown", "Single Game"} else None
    lookup = full_roster_stack_lookup(pool)
    validator = (lambda chosen: offense_vs_defense_allowed(chosen, lookup) and
                 full_roster_stack_matches(chosen, pool, selected_stacks, lookup, secondary_stacks)) if mode_name in {"Classic", "Full Roster"} else single_stack_validator(st, platform_name, mode_name, lookup)
    if mode_name in {"Classic", "Full Roster"}:
        st.caption("Lineup rule: offensive players cannot face their own lineup's defense.")
    progress = st.progress(0, text="Building candidates from joint game outcomes...")
    # Salary-constrained joint outcomes find value. Contest evaluation handles
    # ownership through the field; popular players receive no blanket penalty.
    penalty = None
    seed_patterns = full_roster_stack_patterns(selected_stacks) if mode_name in {"Classic", "Full Roster"} else None
    result = build_candidates(pool, construction, roster, target=5000,
        salary_min=salary_min, salary_max=salary_max, multipliers=multipliers, salary_costs=salary_costs,
        locks=locks, special_allowed=special_allowed, max_from_team=(5 if multipliers else 4 if platform_name=="FanDuel" else 8),
        require_both_teams=True, validator=validator, rng=np.random.default_rng(),
        noise=.08, scenario_diversity=float(np.clip(aggressiveness,0,1)), penalties=penalty, primary_stacks=seed_patterns,
        avoid_opposing_defense=mode_name in {"Classic", "Full Roster"},
        progress=lambda fraction, text: progress.progress(fraction, text=text))
    metadata = dict(result.attrs)
    if result.empty:
        raise ValueError("No legal candidates satisfy the roster, salary, locks and stack requirements")
    result = summarize_candidates(result, evaluation_outcomes, [slot for slot,_ in roster], multipliers)
    metadata["construction_outcomes"] = len(construction)
    metadata["evaluation_outcomes"] = len(evaluation_outcomes)
    metadata["independent_evaluation"] = True
    st.session_state["candidate_engine_" + platform_name + "_" + mode_name] = metadata
    progress.progress(1., text=f"Built {len(result):,} unique candidates from joint outcomes")
    if len(result)<5000:
        st.warning(f"Only {len(result):,} unique legal candidates were found within the bounded search; no duplicates were added to fill the pool. Search diagnostics: " + ", ".join(f"{key}: {value:,}" for key, value in metadata.get("rejected", {}).items()) + ". This is a search limit, not proof that no more legal combinations exist.")
    st.caption("Candidate engine: joint-outcome search; 10,000 separate construction and evaluation outcomes. Lineup percentiles come from summed scores in shared game scripts.")
    return result


def apply_game_weather_context(players_frame, source_frame=None):
    """Resolve actual game venues/kickoffs and annotate weather without changing projections."""
    from datetime import datetime, timedelta, timezone
    from simmah_weather import kickoff_hints, schedule_games, select_game, venue_location, forecast_for_game, team_key
    frame = players_frame.copy()
    now = datetime.now(timezone.utc)
    source = source_frame if isinstance(source_frame, pd.DataFrame) else frame
    hints = kickoff_hints(source.to_dict("records"))
    dates = [value.date() for value in hints.values()]
    start = min(dates) if dates else now.astimezone(ZoneInfo("America/New_York")).date()
    end = (max(dates) + timedelta(days=1)) if dates else start + timedelta(days=8)
    pairs = {}
    for row in frame.to_dict("records"):
        team, opponent = team_key(row.get("Team")), team_key(row.get("Opponent"))
        if team and opponent and opponent not in {"NAN", "NONE", "—", "-"}:
            pairs[tuple(sorted((team, opponent)))] = (team, opponent)
    try:
        if (end-start).days > 14:
            raise ValueError("ambiguous slate dates")
        payload = fetch_game_weather_json(
            f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={start:%Y%m%d}-{end:%Y%m%d}&limit=1000"
        )
        games = schedule_games(payload)
    except Exception:
        games = []

    def fetch_pair(item):
        pair, (team, opponent) = item
        game = select_game(games, team, opponent, now, hints.get(pair))
        if game is None:
            return pair, {"status": "Unavailable: game/kickoff not verified"}
        venue = game["venue"]
        metadata = {"venue": venue.get("fullName", "Unknown venue"),
                    "kickoff": game["kickoff"].isoformat(),
                    "matchup": game["away"] + " @ " + game["home"]}
        location = venue_location(venue)
        if location is None:
            return pair, {**metadata, "status": "Unavailable: venue outside mapped NWS coverage"}
        lat, lon, indoor = location
        if indoor:
            return pair, {**metadata, "status": "Available", "indoor": True,
                          "wind_mph": 0., "precip_pct": 0., "heavy_snow": False,
                          "summary": "Indoor/roofed venue — neutral weather"}
        try:
            point = fetch_game_weather_json(f"https://api.weather.gov/points/{lat},{lon}")
            url = point.get("properties", {}).get("forecastHourly")
            if not url or not str(url).startswith("https://api.weather.gov/"):
                raise ValueError("hourly forecast unavailable")
            hourly = fetch_game_weather_json(url)
            weather = forecast_for_game(hourly.get("properties", {}).get("periods", []), game["kickoff"])
            return pair, {**metadata, **weather, "indoor": False}
        except Exception:
            return pair, {**metadata, "status": "Unavailable: NWS forecast could not load"}

    # Thread workers fetch/parse data only; Streamlit rendering stays on this thread.
    with ThreadPoolExecutor(max_workers=4) as executor:
        contexts = dict(executor.map(fetch_pair, pairs.items()))
    def context(team, opponent):
        return contexts.get(tuple(sorted((team_key(team), team_key(opponent)))),
                            {"status": "Unavailable: matchup not verified"})
    records = [context(row.get("Team"), row.get("Opponent")) for row in frame.to_dict("records")]
    for column, key, default in [
        ("Weather Status", "status", "Unavailable"), ("Weather", "summary", "Unavailable"),
        ("Weather Venue", "venue", "Unknown"), ("Weather Kickoff", "kickoff", ""),
        ("Wind MPH", "wind_mph", np.nan), ("Precip %", "precip_pct", np.nan),
        ("Heavy Snow", "heavy_snow", False), ("Weather Indoor", "indoor", False),
    ]:
        frame[column] = [record.get(key, default) for record in records]
    with st.expander("Game weather — venue and kickoff window", expanded=False):
        summary = []
        for pair, weather in contexts.items():
            kickoff = weather.get("kickoff", "")
            dt = pd.to_datetime(kickoff, utc=True, errors="coerce")
            summary.append({"Game": weather.get("matchup", " / ".join(pair)),
                "Venue": weather.get("venue", "Unknown"),
                "Kickoff (Eastern)": dt.tz_convert("America/New_York").strftime("%m/%d %I:%M %p %Z") if pd.notna(dt) else "Unknown",
                "Status": weather["status"], "Wind MPH": weather.get("wind_mph"),
                "Precip %": weather.get("precip_pct"), "Forecast": weather.get("summary", "Unavailable")})
        if summary:
            st.dataframe(injury_frame(st, pd.DataFrame(summary)), use_container_width=True, hide_index=True)
        else:
            st.caption("Weather unavailable: no verified matchups.")
        st.caption("Both teams use the same game venue and kickoff-to-four-hours-later forecast. Unavailable weather leaves simulation rates unchanged. Source projections are preserved.")
    return frame


def apply_fd_correlated_simulations(sim_df, player_pool, strength=1.0, seed=20261015):
    """Add conservative game/team correlation to FanDuel outcomes only."""
    if not isinstance(sim_df, pd.DataFrame) or sim_df.empty or not isinstance(player_pool, pd.DataFrame) or player_pool.empty:
        return sim_df
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0:
        return sim_df
    needed = {"Name", "Team", "Opponent", "Position"}
    if not needed.issubset(player_pool.columns):
        return sim_df
    meta = player_pool.drop_duplicates("Name", keep="first").set_index("Name")
    cols = [c for c in sim_df.columns if c in meta.index]
    if len(cols) < 2:
        return sim_df
    out = sim_df.copy()
    n = len(out)
    rng = np.random.default_rng(seed)
    game_z, team_z = {}, {}
    for name in cols:
        row = meta.loc[name]
        team = str(row.get("Team", "")).strip().upper()
        opp = str(row.get("Opponent", "")).strip().upper()
        if not team:
            continue
        g = tuple(sorted([team, opp])) if opp else (team,)
        if g not in game_z: game_z[g] = rng.standard_normal(n)
        if team not in team_z: team_z[team] = rng.standard_normal(n)
    for name in cols:
        row = meta.loc[name]
        team = str(row.get("Team", "")).strip().upper()
        opp = str(row.get("Opponent", "")).strip().upper()
        pos = str(row.get("Position", "")).strip().upper().replace("DST", "D")
        if not team:
            continue
        g = tuple(sorted([team, opp])) if opp else (team,)
        gz, tz, oz = game_z.get(g), team_z.get(team), team_z.get(opp) if opp else None
        if gz is None or tz is None:
            continue
        if pos == "QB": shock = 0.16 * gz + 0.22 * tz
        elif pos in {"WR", "TE"}: shock = 0.18 * gz + 0.24 * tz
        elif pos == "RB": shock = 0.12 * gz + 0.18 * tz - (0.06 * oz if oz is not None else 0.0)
        elif pos in {"D", "DEF"}: shock = -0.10 * gz + 0.16 * tz - (0.18 * oz if oz is not None else 0.0)
        elif pos == "K": shock = 0.10 * gz + 0.12 * tz
        else: shock = 0.12 * gz + 0.15 * tz
        vals = pd.to_numeric(out[name], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        old_mean, old_sd = float(np.mean(vals)), float(np.std(vals))
        if old_sd <= 0: continue
        vals2 = vals + (shock * strength) * old_sd
        new_sd = float(np.std(vals2))
        if new_sd > 0:
            vals2 = old_mean + (vals2 - float(np.mean(vals2))) * (old_sd / new_sd)
        out[name] = np.maximum(vals2, 0.0)
    return out


@st.cache_data(ttl=86400, max_entries=8, show_spinner=False)
def fit_projection_event_inputs_cached(pool, roles, platform, model_version):
    # Keep cached execution free of external Streamlit layout objects.
    from simmah_projection_inputs import fit_projection_inputs
    return fit_projection_inputs(pool, roles, platform, score_nfl_stat_line)


def simulation_cache_root():
    from pathlib import Path
    import os
    configured = os.environ.get("SIMMAH_SIMULATION_CACHE_DIR")
    return Path(configured) if configured else Path(__file__).resolve().parent / "data" / "simulation_cache"


@st.cache_data(show_spinner=False, ttl=86400)
def load_matchup_schedule():
    try:
        response = requests.get("https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv", timeout=(4, 10))
        response.raise_for_status()
        import io
        return pd.read_csv(io.StringIO(response.text), usecols=["game_id", "gameday"])
    except Exception:
        return pd.DataFrame(columns=["game_id", "gameday"])


def simulate_fd_play_by_play(players_df, rng, n=SIMULATION_COUNT, correlation_strength=1.0, platform="FanDuel"):
    """Prepare or reuse separate shared game samples with exact DFS scoring.

    rng is retained for call compatibility; persisted sample seeds belong to the
    preparation key. Candidate sampling remains randomized on each BUILD.
    """
    from simmah_nfl_engine import ENGINE_VERSION
    if not isinstance(players_df, pd.DataFrame) or players_df.empty:
        return pd.DataFrame()
    n = max(1, int(n))
    pool = players_df.drop_duplicates("Name", keep="first").copy().reset_index(drop=True)
    for col in ("Name", "Team", "Opponent", "Position"):
        if col not in pool.columns:
            pool[col] = ""
    pool["Projection"] = pd.to_numeric(pool.get("Projection", 0.0), errors="coerce").fillna(0.01).clip(lower=0.01)
    _fd_hist = load_nfl_historical_player_stats()
    # The historical index retains spaces; use the same canonical keys as
    # salary/projection names before looking up opportunity profiles.
    _fd_hist_index = {
        normalize_projection_player_name(name): rows
        for name, rows in _build_historical_name_index(_fd_hist).items()
    } if not _fd_hist.empty else {}
    # Historical opportunity/efficiency profiles for every offensive position.
    # These feed the play generator itself; they do not add fantasy points after simulation.
    _fd_hist_roles = {}
    if not _fd_hist.empty:
        for _, _row in pool.iterrows():
            _name = str(_row.get("Name", ""))
            _pos = str(_row.get("Position", "")).upper().split("/")[0].strip()
            if _pos not in {"QB", "RB", "WR", "TE", "K"}:
                continue
            try:
                _matched_history = _fd_hist_index.get(normalize_projection_player_name(_name))
                if _matched_history is None or not isinstance(_matched_history, pd.DataFrame) or _matched_history.empty:
                    continue
                _rows = _matched_history.copy()
                if _rows.empty:
                    continue
                if "season" in _rows.columns and "week" in _rows.columns:
                    _rows = _rows.sort_values(["season", "week"]).tail(24)
                def _avg(*cols):
                    c = next((x for x in cols if x in _rows.columns), None)
                    return float(pd.to_numeric(_rows[c], errors="coerce").fillna(0).clip(lower=0).mean()) if c else 0.0
                _fd_hist_roles[_name] = {
                    "carries": _avg("carries", "rushing_attempts", "rush_attempts"),
                    "targets": _avg("targets"),
                    "receptions": _avg("receptions"),
                    "rush_yards": _avg("rushing_yards", "rush_yards"),
                    "rec_yards": _avg("receiving_yards", "rec_yards"),
                    "rush_tds": _avg("rushing_tds", "rushing_touchdowns", "rush_tds"),
                    "rec_tds": _avg("receiving_tds", "receiving_touchdowns", "rec_tds"),
                    "pass_attempts": _avg("attempts", "passing_attempts"),
                    "completions": _avg("completions", "passing_completions"),
                    "pass_yards": _avg("passing_yards", "pass_yards"),
                    "pass_tds": _avg("passing_tds", "passing_touchdowns", "pass_tds"),
                    "interceptions": _avg("interceptions", "passing_interceptions"),
                }
            except Exception:
                continue

    from simmah_matchups import matchup_inputs
    _matchup_roles, _matchup_report = matchup_inputs(pool, _fd_hist, load_matchup_schedule())
    for _name, _context in _matchup_roles.items():
        _fd_hist_roles.setdefault(_name, {}).update(_context)
    with st.expander("Defensive matchup context", expanded=False):
        st.caption("nflverse weekly statistics; only dated games before kickoff. Minimum four games; rates shrink toward league averages. External projections remain the scoring targets. Neutral when data is unavailable.")
        st.dataframe(injury_frame(st, _matchup_report), hide_index=True, use_container_width=True)

    progress = st.progress(0, text=f"Preparing {n:,} independent NFL game outcomes...")
    from simmah_weather import team_key
    weather_by_team = {}
    for row in pool.to_dict("records"):
        weather_by_team[team_key(row.get("Team"))] = {
            "status": row.get("Weather Status", "Unavailable"),
            "wind_mph": row.get("Wind MPH", 0), "precip_pct": row.get("Precip %", 0),
            "heavy_snow": row.get("Heavy Snow", False), "indoor": row.get("Weather Indoor", False),
        }
    from simmah_simulation_store import prepare_simulations, weather_snapshot
    weather_by_team = weather_snapshot(pool)
    _fit_pool = pool[["Name", "Team", "Opponent", "Position", "Projection"]].copy()
    prepared = prepare_simulations(_fit_pool, _fd_hist_roles, platform, simulation_cache_root(),
        count=n, correlation_strength=correlation_strength, weather_by_team=weather_by_team,
        market_targets=st.session_state.get("active_game_markets", {}),
        progress=lambda fraction,text: progress.progress(fraction,text=text))
    result = prepared["evaluation"].copy()
    result.attrs["preparation_key"] = prepared["metadata"]["key"]
    _projection_fit_report = prepared["fit_report"]
    st.session_state["simulation_preparation_" + platform] = prepared["metadata"]
    _prep_timing = prepared["metadata"]["timings"]
    st.caption("Prepared simulation cache: " + ("reused" if prepared["metadata"]["cache_hit"] else "created") +
        f"; {n:,} evaluation and {n:,} separate construction outcomes. " +
        ", ".join(f"{stage}: {seconds:.2f}s" for stage,seconds in _prep_timing.items()))
    _projection_fit_report = _projection_fit_report.copy()
    _projection_fit_report["Actual Simulation Mean"] = _projection_fit_report["Name"].map(result.mean().to_dict())
    _projection_fit_report["Simulation Minus Projection"] = _projection_fit_report["Actual Simulation Mean"] - _projection_fit_report["Projection"]
    st.session_state["projection_event_fit_" + platform] = _projection_fit_report
    _fit_offense = _projection_fit_report[_projection_fit_report["Calibration Status"].eq("Event inputs fitted")]
    if not _fit_offense.empty:
        _fit_mae = _fit_offense["Simulation Minus Projection"].abs().mean()
        st.caption(f"Projection-informed event inputs: offensive-player mean absolute difference {_fit_mae:.2f} points. Prepared independent game paths retain shared stats; means are not forced to equal projections. Defense and kicker rates are not fitted by this calibration.")
    result.attrs["engine_version"] = ENGINE_VERSION
    result.attrs["independent_outcomes"] = n
    best = result.max(axis=1)
    ties = result.eq(best, axis=0)
    cap_hit = ties.div(ties.sum(axis=1).clip(lower=1), axis=0).mean() * 100
    st.session_state["simulation_cap_hit_pct"] = cap_hit.to_dict()
    progress.progress(1.0, text=f"Completed {n:,} independent NFL outcomes ({ENGINE_VERSION})")
    return result


if platform == "FanDuel":
    fd_slate_file = auto_slate_file
    fd_file = fd_slate_file
    fd_entry_file = fd_slate_file

    with _contest_setup:
        st.write("### Contest Selector")
        if fd_entry_file is not None:
            try:
                # FanDuel entry templates contain multiple sections with different
                # column counts. Read only the first contiguous entry table instead
                # of asking pandas to parse the player-reference section as entries.
                import csv
                import io
                fd_entry_file.seek(0)
                fd_template_text = fd_entry_file.getvalue().decode("utf-8-sig", errors="replace")
                fd_template_rows = list(csv.reader(io.StringIO(fd_template_text)))
                if not fd_template_rows:
                    raise ValueError("The uploaded FanDuel entry template is empty.")
                fd_template_header = [str(c).strip() for c in fd_template_rows[0]]
                fd_entry_rows = []
                for template_row in fd_template_rows[1:]:
                    if not template_row or not str(template_row[0]).strip():
                        break
                    normalized_row = list(template_row[:len(fd_template_header)])
                    normalized_row.extend([""] * (len(fd_template_header) - len(normalized_row)))
                    fd_entry_rows.append(normalized_row)
                fd_entry_df = pd.DataFrame(fd_entry_rows, columns=fd_template_header)
                fd_entry_lookup = {str(c).strip().casefold(): c for c in fd_entry_df.columns}
                fd_name_col = next((fd_entry_lookup[k] for k in (
                    "contest name", "contest_name", "contestname", "contest"
                ) if k in fd_entry_lookup), None)
                fd_id_col = next((fd_entry_lookup[k] for k in (
                    "contest id", "contest_id", "contestid"
                ) if k in fd_entry_lookup), None)
                fd_entries_col = next((fd_entry_lookup[k] for k in (
                    "entry id", "entry_id", "entryid"
                ) if k in fd_entry_lookup), None)
                fd_fee_col = next((fd_entry_lookup[k] for k in (
                    "entry fee", "entry_fee", "entryfee", "fee"
                ) if k in fd_entry_lookup), None)
                if fd_name_col is None or fd_id_col is None:
                    st.error("This CSV needs Contest Name and Contest ID columns for the contest selector.")
                else:
                    fd_entry_df[fd_id_col] = fd_entry_df[fd_id_col].astype(str).str.replace(r"\.0$", "", regex=True)
                    fd_entry_df = remove_duplicate_entries(fd_entry_df, fd_entries_col)
                    fd_entry_df = fd_entry_df[
                        fd_entry_df[fd_name_col].apply(is_full_game_contest_name)
                    ].copy()
                    if fd_entry_df.empty:
                        st.warning("No full-game FanDuel contests were found in this entry file.")
                    fd_group_columns = [fd_id_col, fd_name_col]
                    fd_agg = {
                        "Entries": (fd_entries_col, "count") if fd_entries_col else (fd_id_col, "size"),
                        "EntryFee": (fd_fee_col, "first") if fd_fee_col else (fd_id_col, "size"),
                    }
                    fd_contest_summary = fd_entry_df.groupby(fd_group_columns, dropna=False).agg(**fd_agg).reset_index()
                    fd_contest_summary["Contest Label"] = fd_contest_summary.apply(
                        lambda row: f"{row[fd_name_col]} | ID {row[fd_id_col]} | {int(row['Entries'])} of your entries",
                        axis=1
                    )
                    fd_selected_label = st.selectbox(
                        "Select the FanDuel contest to simulate against",
                        fd_contest_summary["Contest Label"].tolist(),
                        key="fd_selected_contest"
                    )
                    fd_selected_row = fd_contest_summary.loc[
                        fd_contest_summary["Contest Label"].eq(fd_selected_label)
                    ].iloc[0]
                    fd_fee = pd.to_numeric(
                        str(fd_selected_row["EntryFee"]).replace("$", "").replace(",", ""),
                        errors="coerce"
                    )
                    _fd_contest_id = str(fd_selected_row[fd_id_col])
                    _fd_auto_details = fetch_fanduel_contest_details(_fd_contest_id)
                    st.session_state["selected_fd_contest"] = {
                        "id": _fd_contest_id,
                        "name": str(fd_selected_row[fd_name_col]),
                        "your_entries": int(fd_selected_row["Entries"]),
                        "entry_fee": float(fd_fee) if pd.notna(fd_fee) else None,
                        "field_size": (_fd_auto_details or {}).get("field_size"),
                        "current_entries": (_fd_auto_details or {}).get("current_entries"),
                        "max_entries_per_user": (_fd_auto_details or {}).get("max_entries_per_user"),
                        "prize_pool": (_fd_auto_details or {}).get("prize_pool"),
                        "prize_summary": (_fd_auto_details or {}).get("prize_summary"),
                    }
                    if _fd_contest_id == "135541-281148543":
                        _fd_verified = full_roster_contest_parameters(st.session_state["selected_fd_contest"], 10000)
                        st.session_state["selected_fd_contest"].update(
                            field_size=_fd_verified["field_size"], payouts=_fd_verified["tiers"],
                            entry_fee=_fd_verified["fee"], max_entries_per_user=150,
                            prize_pool=20000, prize_summary="28,750 paid places; $500 first")
                        st.caption("Verified Hail Mary payouts: $20,000 across 28,750 paid places. ROI models the full 95,808-entry capacity; the final filled field may differ.")
                    if _fd_contest_id == "135464-281110099":
                        st.caption("Confirmed Pooch Punt payout schedule: $4,000 across 28,750 paid places. ROI models the full 95,808-entry capacity; the final filled field may differ.")
                    fd_fee_text = f"${float(fd_fee):.2f}" if pd.notna(fd_fee) else "not listed"
                    st.success(
                        f"Selected: {fd_selected_row[fd_name_col]} | Contest ID: {_fd_contest_id} | "
                        f"Your entries: {int(fd_selected_row['Entries'])} | Entry fee: {fd_fee_text}"
                    )
                    if _fd_auto_details:
                        _fd_bits = []
                        if _fd_auto_details.get("field_size"):
                            _fd_bits.append(f"Field size: {int(_fd_auto_details['field_size']):,}")
                        if _fd_auto_details.get("max_entries_per_user"):
                            _fd_bits.append(f"Max entries/user: {int(_fd_auto_details['max_entries_per_user']):,}")
                        if _fd_auto_details.get("prize_pool"):
                            _fd_bits.append(f"Prize pool: ${float(_fd_auto_details['prize_pool']):,.2f}")
                        if _fd_auto_details.get("prize_summary"):
                            _fd_bits.append(f"Prizes: {_fd_auto_details['prize_summary']}")
                        st.info("FanDuel contest lookup: " + (" | ".join(_fd_bits) if _fd_bits else "contest found"))
                    else:
                        st.caption(
                            "FanDuel contest ID, name, fee, and your entries were loaded from the CSV. "
                            "FanDuel did not expose the full field size/payout details publicly for this contest, so those details cannot be verified automatically yet."
                        )
            except Exception as exc:
                st.error(f"Could not read the FanDuel contest entry file: {exc}")

        from simmah_saved_contests import render_panel as render_saved_contest_panel
        st.session_state["selected_fd_contest"] = render_saved_contest_panel(
            st, st.session_state.get("selected_fd_contest", {}), selected_format)

        fd_opponent_target = get_contest_opponent_target("fd")
        st.caption(f"Simulated FanDuel opponents: up to {fd_opponent_target:,} (speed limit)")

    with _tab_roster:
        st.write("### Projection Sources")
        with st.expander("Upload projections / restore saved pregame inputs", expanded=False):
            st.caption("Uploads take priority over automatic projections. To restore saved point projections, upload the pregame player-input CSV below.")
            _fd_saved_projection_file = workspace_file_uploader(st,
                "Saved pregame player inputs CSV", type=["csv"],
                key="fd_saved_projection_upload_" + lineup_mode.replace(" ", "_").lower())
            _fd_projection_cols = st.columns(2)
            with _fd_projection_cols[0]:
                _fd_manual_dff = workspace_file_uploader(st,"DFF projections CSV (optional)", type=["csv"],
                    key="fd_dff_projection_upload_" + lineup_mode.replace(" ", "_").lower())
            with _fd_projection_cols[1]:
                _fd_manual_draftedge = workspace_file_uploader(st,"DraftEdge projections CSV (optional)", type=["csv"],
                    key="fd_draftedge_projection_upload_" + lineup_mode.replace(" ", "_").lower())
            if _fd_saved_projection_file is not None:
                st.caption("Saved point projections supplied to both sources to preserve the saved averages. Injury and weather checks remain current.")
        fd_dff_projection_file = _fd_saved_projection_file if _fd_saved_projection_file is not None else _fd_manual_dff
        fd_draftedge_projection_file = _fd_saved_projection_file if _fd_saved_projection_file is not None else _fd_manual_draftedge
        show_projection_refresh_status(
            [("DFF", fd_dff_projection_file), ("DraftEdge", fd_draftedge_projection_file)],
            "fd_" + lineup_mode.replace(" ", "_").lower()
        )

        if fd_file is None:
            st.info("Upload your FanDuel slate/entries CSV to load the slate and build lineups.")
            workspace_stop(st, _loaded_slate_tabs)

        try:
            # FanDuel exports may include preamble rows or inconsistent rows before
            # the actual player table. Find the real header row before parsing.
            import csv
            import io

            fd_text = fd_file.getvalue().decode("utf-8-sig", errors="replace")
            fd_lines = fd_text.splitlines()
            fd_header_line = None
            for line_index, line in enumerate(fd_lines[:500]):
                try:
                    cells = next(csv.reader([line]))
                except Exception:
                    continue
                normalized = {str(cell).strip().lower() for cell in cells}
                has_name = bool(normalized & {"nickname", "name", "name + id", "player", "player name"})
                has_salary = "salary" in normalized
                has_team = bool(normalized & {"team", "teamabbrev", "team abbrev", "team abbreviation"})
                has_position = bool(normalized & {"position", "roster position", "rosterposition"})
                if has_name and has_salary and has_team and has_position:
                    fd_header_line = line_index
                    break

            if fd_header_line is None:
                fd_raw = pd.read_csv(io.StringIO(fd_text), engine="python", on_bad_lines="skip")
            else:
                fd_raw = pd.read_csv(
                    io.StringIO(fd_text),
                    skiprows=fd_header_line,
                    engine="python",
                    on_bad_lines="skip"
                )
            fd_raw.columns = [str(c).strip() for c in fd_raw.columns]

            def fd_find_column(frame, choices):
                lookup = {str(c).strip().lower(): c for c in frame.columns}
                for choice in choices:
                    if choice.lower() in lookup:
                        return lookup[choice.lower()]
                return None

            fd_name_col = fd_find_column(
                fd_raw, ["Nickname", "Name", "Name + ID", "Player", "Player Name"]
            )
            fd_salary_col = fd_find_column(fd_raw, ["Salary"])
            fd_team_col = fd_find_column(
                fd_raw, ["Team", "TeamAbbrev", "Team Abbrev", "Team Abbreviation"]
            )
            fd_pos_col = fd_find_column(
                fd_raw, ["Position", "Roster Position", "RosterPosition"]
            )
            # Never use FanDuel's salary-file fantasy average as a projection.
            fd_proj_col = None
            fd_id_col = fd_find_column(
                fd_raw, ["Id", "ID", "Player ID", "FDP_ID", "PlayerId"]
            )

            missing_cols = []
            if fd_name_col is None:
                missing_cols.append("player name (Nickname or Name)")
            if fd_salary_col is None:
                missing_cols.append("Salary")
            if fd_team_col is None:
                missing_cols.append("Team")
            if fd_pos_col is None:
                missing_cols.append("Position")

            if missing_cols:
                st.error("Missing required columns: " + ", ".join(missing_cols))
                workspace_stop(st, _loaded_slate_tabs)

            fd_players = pd.DataFrame()
            fd_players["Name"] = fd_raw[fd_name_col].astype(str).str.strip()
            fd_players["Name"] = fd_players["Name"].str.replace(
                r"\s*\(\d+\)\s*$", "", regex=True
            )
            fd_players["Salary"] = pd.to_numeric(
                fd_raw[fd_salary_col].astype(str).str.replace(r"[$,]", "", regex=True),
                errors="coerce"
            )
            fd_players["Team"] = fd_raw[fd_team_col].astype(str).str.strip().str.upper()
            for _game_col in fd_raw.columns:
                if str(_game_col).lower().replace(" ", "") in {"gameinfo", "game", "starttime", "kickoff"}:
                    fd_players[_game_col] = fd_raw[_game_col]

            show_detected_slate_games(fd_raw)
            fd_opponent_col = fd_find_column(fd_raw, ["Opponent", "Opp"])
            if fd_opponent_col is not None:
                fd_players["Opponent"] = (
                    fd_raw[fd_opponent_col].astype(str).str.strip().str.upper()
                    .replace({"": np.nan, "NAN": np.nan, "NONE": np.nan, "-": np.nan, "—": np.nan})
                )
                # Only use the Game-column fallback for rows where FanDuel did not supply Opponent.
                fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
                fd_players["Opponent"] = fd_players["Opponent"].fillna(fd_players["Team"].map(fd_opponents)).fillna("—")
            else:
                fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
                fd_players["Opponent"] = fd_players["Team"].map(fd_opponents).fillna("—")
            fd_players["Position"] = fd_raw[fd_pos_col].astype(str).str.strip().str.upper()
            # Do not invent projections from salary. The external-source loader below
            # fills this column with DFF/DraftEdge values or NaN if neither source matches.
            fd_players["Projection"] = np.nan
            if fd_id_col is not None:
                fd_players["FD_ID"] = fd_raw[fd_id_col].astype(str).str.strip()

            fd_players = preserve_uploaded_ownership(fd_players, fd_raw)
            fd_players = fd_players.dropna(subset=["Salary"])
            fd_players = fd_players[
                (fd_players["Name"] != "") &
                (fd_players["Name"].str.lower() != "nan") &
                (fd_players["Salary"] > 0)
            ].drop_duplicates(subset=["Name"], keep="first").reset_index(drop=True)

            if fd_players.empty:
                st.error("No usable players were found in that CSV.")
                workspace_stop(st, _loaded_slate_tabs)

        except Exception as exc:
            st.error(f"Could not read that FanDuel CSV: {exc}")
            workspace_stop(st, _loaded_slate_tabs)

        fd_projection_platform = "FanDuel Single Game" if lineup_mode == "Single Game" else "FanDuel Full Roster"
        fd_players = apply_external_projection_sources(
            fd_players, fd_dff_projection_file, fd_draftedge_projection_file,
            platform_name=fd_projection_platform
        )
        if lineup_mode == "Full Roster":
            fd_defense_aliases = {
                "ARI": ["Arizona Cardinals", "Cardinals", "Arizona"],
                "ATL": ["Atlanta Falcons", "Falcons", "Atlanta"],
                "BAL": ["Baltimore Ravens", "Ravens", "Baltimore"],
                "BUF": ["Buffalo Bills", "Bills", "Buffalo"],
                "CAR": ["Carolina Panthers", "Panthers", "Carolina"],
                "CHI": ["Chicago Bears", "Bears", "Chicago"],
                "CIN": ["Cincinnati Bengals", "Bengals", "Cincinnati"],
                "CLE": ["Cleveland Browns", "Browns", "Cleveland"],
                "DAL": ["Dallas Cowboys", "Cowboys", "Dallas"],
                "DEN": ["Denver Broncos", "Broncos", "Denver"],
                "DET": ["Detroit Lions", "Lions", "Detroit"],
                "GB": ["Green Bay Packers", "Packers", "Green Bay"],
                "HOU": ["Houston Texans", "Texans", "Houston"],
                "IND": ["Indianapolis Colts", "Colts", "Indianapolis"],
                "JAX": ["Jacksonville Jaguars", "Jaguars", "Jacksonville"],
                "KC": ["Kansas City Chiefs", "Chiefs", "Kansas City"],
                "LV": ["Las Vegas Raiders", "Raiders", "Las Vegas"],
                "LAC": ["Los Angeles Chargers", "Chargers", "LA Chargers"],
                "LAR": ["Los Angeles Rams", "Rams", "LA Rams"],
                "MIA": ["Miami Dolphins", "Dolphins", "Miami"],
                "MIN": ["Minnesota Vikings", "Vikings", "Minnesota"],
                "NE": ["New England Patriots", "Patriots", "New England"],
                "NO": ["New Orleans Saints", "Saints", "New Orleans"],
                "NYG": ["New York Giants", "Giants", "NY Giants"],
                "NYJ": ["New York Jets", "Jets", "NY Jets"],
                "PHI": ["Philadelphia Eagles", "Eagles", "Philadelphia"],
                "PIT": ["Pittsburgh Steelers", "Steelers", "Pittsburgh"],
                "SEA": ["Seattle Seahawks", "Seahawks", "Seattle"],
                "SF": ["San Francisco 49ers", "49ers", "San Francisco"],
                "TB": ["Tampa Bay Buccaneers", "Buccaneers", "Tampa Bay", "Bucs"],
                "TEN": ["Tennessee Titans", "Titans", "Tennessee"],
                "WAS": ["Washington Commanders", "Commanders", "Washington"],
            }
            fd_dff_all, _ = get_projection_source_data(
                fd_dff_projection_file, "DFF", fd_projection_platform,
                target_names=fd_players["Name"].astype(str).tolist()
            )
            fd_edge_all, _ = get_projection_source_data(
                fd_draftedge_projection_file, "DraftEdge", fd_projection_platform,
                target_names=fd_players["Name"].astype(str).tolist()
            )
            fd_def_mask = fd_players["Position"].astype(str).str.upper().isin(["D", "DST", "DEF"])
            for fd_idx in fd_players.index[fd_def_mask]:
                if pd.notna(pd.to_numeric(fd_players.at[fd_idx, "Projection"], errors="coerce")) and float(fd_players.at[fd_idx, "Projection"]) > 0:
                    continue
                fd_team = str(fd_players.at[fd_idx, "Team"]).strip().upper()
                aliases = [str(fd_players.at[fd_idx, "Name"]), fd_team] + fd_defense_aliases.get(fd_team, [])
                alias_keys = [normalize_projection_player_name(alias) for alias in aliases]
                dff_value = next((fd_dff_all.get(key) for key in alias_keys if fd_dff_all.get(key) is not None), None)
                edge_value = next((fd_edge_all.get(key) for key in alias_keys if fd_edge_all.get(key) is not None), None)
                if dff_value is not None and edge_value is not None:
                    fd_players.at[fd_idx, "Projection"] = (float(dff_value) + float(edge_value)) / 2.0
                    fd_players.at[fd_idx, "ProjectionSource"] = "DFF + DraftEdge average"
                elif dff_value is not None:
                    fd_players.at[fd_idx, "Projection"] = float(dff_value)
                    fd_players.at[fd_idx, "ProjectionSource"] = "DFF"
                elif edge_value is not None:
                    fd_players.at[fd_idx, "Projection"] = float(edge_value)
                    fd_players.at[fd_idx, "ProjectionSource"] = "DraftEdge"
        fd_valid_projection_count = int(pd.to_numeric(fd_players.get("Projection"), errors="coerce").gt(0).sum())
        if fd_valid_projection_count == 0 and not fd_players.empty:
            st.warning(
                "Players loaded successfully, but external projections are not available for this slate yet. "
                "Click REFRESH PROJECTIONS + INJURY NEWS later after projections are posted."
            )
        elif fd_valid_projection_count < len(fd_players):
            st.info(
                f"Players loaded successfully. Projections are available for {fd_valid_projection_count} of {len(fd_players)} players; "
                "players without a posted external projection will stay out of builds until a refresh finds one."
            )
        fd_players = exclude_zero_projection_players(fd_players, "FanDuel " + lineup_mode)
        fd_players = apply_injury_statuses(fd_players, "injury_status_fd_" + lineup_mode.replace(" ", "_").lower())
        fd_players = resolve_quarterback_roles_for_build(fd_players, "FanDuel " + lineup_mode)

        # Restore FanDuel's saved simulation summaries on every Streamlit rerun.
        fd_sim_key = "fd_player_sim_" + lineup_mode.replace(" ", "_").lower()
        player_sim = st.session_state.get(fd_sim_key, {})
        _fd_measured_outcomes = st.session_state.get(
            "fd_simulation_df_" + lineup_mode.replace(" ", "_").lower())
        if (isinstance(player_sim, dict) and isinstance(_fd_measured_outcomes, pd.DataFrame)
                and not _fd_measured_outcomes.empty):
            player_sim = {name: summary for name, summary in player_sim.items()
                          if name in _fd_measured_outcomes.columns}
        else:
            player_sim = {}
        # Leave simulation columns pending until real outcomes exist. External
        # projections remain in Projection; fixed multiples are not percentiles.
        # Remove stale saved builds as soon as an Out player is excluded.
        fd_allowed_names = set(fd_players["Name"].astype(str))
        for saved_key in list(st.session_state.get("fd_saved_builds", {}).keys()):
            saved_lineups = st.session_state["fd_saved_builds"][saved_key].get("lineups")
            if isinstance(saved_lineups, pd.DataFrame):
                lineup_columns = [c for c in saved_lineups.columns if c not in {"Salary", "ProjectedPoints", "Score"}]
                if any(saved_lineups[col].astype(str).isin(
                    set(fd_raw[fd_name_col].astype(str).str.replace(r"\s*\(\d+\)\s*$", "", regex=True).str.strip()) - fd_allowed_names
                ).any() for col in lineup_columns if col in saved_lineups.columns):
                    st.session_state["fd_saved_builds"].pop(saved_key, None)

        st.divider()
        st.write("### Player Pool — Stats, Simulation, Exposure & Controls")
        st.success(f"Loaded {len(fd_players)} FanDuel players after injury-status filtering.")
        if fd_proj_col is None:
            st.caption(
                "FanDuel salary-file averages are ignored. Check ProjectionSource "
                "in the player table to see whether DFF or DraftEdge matched. "
                "Players without a valid positive external projection are excluded."
            )
        fd_player_display = fd_players.drop(columns=["FD_ID"], errors="ignore").copy()
        # FanDuel Full Roster uses the same useful player-pool information as DK Classic.
        # Simulation columns are restored immediately from the saved/current simulation.
        for sim_key, sim_label in [
            ("Mean", "Sim Pts"), ("P10", "Sim P10"), ("P25", "Sim P25"),
            ("P50", "Sim P50"), ("P75", "Sim P75"), ("P90", "Sim P90"),
            ("P95", "Sim P95"), ("P99", "Sim P99"),
        ]:
            fd_player_display[sim_label] = fd_player_display["Name"].astype(str).map(
                lambda name, key=sim_key: pd.to_numeric(player_sim.get(str(name), {}).get(key), errors="coerce")
            )
        _fd_cap_hit_key = "fd_simulation_cap_hit_pct_" + lineup_mode.replace(" ", "_").lower()
        _fd_cap_hits = st.session_state.get(_fd_cap_hit_key, {})
        fd_player_display["Cap Hit %"] = fd_player_display["Name"].astype(str).map(
            lambda name: pd.to_numeric(_fd_cap_hits.get(str(name)), errors="coerce")
        )
        if "Lock" not in fd_player_display.columns:
            fd_player_display["Lock"] = False
        if "Fade" not in fd_player_display.columns:
            fd_player_display["Fade"] = False
        if "Min Exposure %" not in fd_player_display.columns:
            fd_player_display["Min Exposure %"] = 0
        if "Max Exposure %" not in fd_player_display.columns:
            fd_player_display["Max Exposure %"] = 100
        # Full Roster has no captain/MVP exposure controls.
        if lineup_mode == "Full Roster":
            fd_player_display = fd_player_display.drop(
                columns=["Captain Min %", "Captain Max %", "MVP Min %", "MVP Max %"],
                errors="ignore"
            )
        # Show exposure from the active FanDuel slate only.
        fd_build_key = "fd_lineups_" + lineup_mode.replace(" ", "_").lower()
        fd_current_lineups = st.session_state.get(fd_build_key)
        if isinstance(fd_current_lineups, pd.DataFrame) and not fd_current_lineups.empty:
            fd_total = len(fd_current_lineups)
            fd_slot_columns = [
                c for c in fd_current_lineups.columns
                if c.upper() in {"MVP", "FLEX", "FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5", "QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "D"}
            ]
            player_names = fd_player_display["Name"].astype(str).str.strip()
            fd_player_display["Exposure %"] = player_names.map(
                lambda name: round(100 * sum(
                    fd_current_lineups[c].astype(str).str.strip().eq(name).sum()
                    for c in fd_slot_columns
                ) / fd_total, 1)
            )
            if lineup_mode == "Single Game":
                mvp_column = next((c for c in fd_current_lineups.columns if c.upper() == "MVP"), None)
                flex_columns = [c for c in fd_current_lineups.columns if c.upper().startswith("FLEX")]
                if mvp_column:
                    fd_player_display["MVP Exp %"] = player_names.map(
                        lambda name: round(100 * fd_current_lineups[mvp_column].astype(str).str.strip().eq(name).sum() / fd_total, 1)
                    )
                else:
                    fd_player_display["MVP Exp %"] = 0.0
                if flex_columns:
                    flex_appearances = (
                        fd_current_lineups[flex_columns]
                        .astype(str)
                        .apply(lambda row: pd.unique(row.str.strip()).tolist(), axis=1)
                        .explode()
                        .value_counts()
                    )
                    fd_player_display["Flex Exp %"] = player_names.map(
                        lambda name: round(100 * flex_appearances.get(name, 0) / fd_total, 1)
                    )
                else:
                    fd_player_display["Flex Exp %"] = 0.0
            else:
                fd_player_display = fd_player_display.drop(
                    columns=["MVP Exp %", "Flex Exp %"], errors="ignore"
                )
        else:
            fd_player_display["Exposure %"] = np.nan
            if lineup_mode == "Single Game":
                fd_player_display["MVP Exp %"] = np.nan
                fd_player_display["Flex Exp %"] = np.nan
            else:
                fd_player_display = fd_player_display.drop(
                    columns=["MVP Exp %", "Flex Exp %"], errors="ignore"
                )

        # Put simulated field ownership directly in the visible FanDuel Player Pool.
        fd_ownership_by_format = st.session_state.get("latest_field_ownership_by_format", {})
        fd_visible_field = fd_ownership_by_format.get(selected_format) if isinstance(fd_ownership_by_format, dict) else None

        # Rebuild missing FanDuel field ownership directly from this format's simulated
        # opponent field. Single Game keeps MVP and FLEX ownership separate.
        if not isinstance(fd_visible_field, pd.DataFrame) or fd_visible_field.empty:
            _fd_field_key = "fd_contest_field_" + lineup_mode.replace(" ", "_").lower()
            _fd_active_field = st.session_state.get(_fd_field_key)
            if lineup_mode == "Single Game":
                _fd_role_col = "MVP"
                _fd_field_slots = [c for c in ["MVP", "FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5"] if isinstance(_fd_active_field, pd.DataFrame) and c in _fd_active_field.columns]
            else:
                _fd_role_col = None
                _fd_field_slots = [c for c in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "D"] if isinstance(_fd_active_field, pd.DataFrame) and c in _fd_active_field.columns]

            if isinstance(_fd_active_field, pd.DataFrame) and not _fd_active_field.empty and _fd_field_slots:
                _fd_field_total = len(_fd_active_field)
                _fd_all_counts = (
                    _fd_active_field[_fd_field_slots]
                    .astype(str)
                    .apply(lambda row: pd.unique(row.str.strip()).tolist(), axis=1)
                    .explode()
                    .value_counts()
                )
                _fd_field_names = fd_player_display["Name"].astype(str).str.strip()
                fd_visible_field = pd.DataFrame({
                    "Name": _fd_field_names,
                    "Ownership %": _fd_field_names.map(lambda n: 100.0 * _fd_all_counts.get(n, 0) / max(_fd_field_total, 1)),
                })
                if _fd_role_col is not None and _fd_role_col in _fd_active_field.columns:
                    _fd_role_counts = _fd_active_field[_fd_role_col].astype(str).str.strip().value_counts()
                    fd_visible_field["Captain/MVP Ownership %"] = _fd_field_names.map(
                        lambda n: 100.0 * _fd_role_counts.get(n, 0) / max(_fd_field_total, 1)
                    )
                if not isinstance(fd_ownership_by_format, dict):
                    fd_ownership_by_format = {}
                fd_ownership_by_format[selected_format] = fd_visible_field.copy()
                st.session_state["latest_field_ownership_by_format"] = fd_ownership_by_format

        if isinstance(fd_visible_field, pd.DataFrame) and not fd_visible_field.empty and "Name" in fd_visible_field.columns:
            fd_names_for_field = fd_player_display["Name"].astype(str).str.strip()
            fd_overall_map = dict(zip(
                fd_visible_field["Name"].astype(str).str.strip(),
                pd.to_numeric(fd_visible_field.get("Ownership %"), errors="coerce")
            ))
            fd_overall = fd_names_for_field.map(fd_overall_map)
            if lineup_mode == "Single Game":
                if "Captain/MVP Ownership %" in fd_visible_field.columns:
                    fd_mvp_map = dict(zip(
                        fd_visible_field["Name"].astype(str).str.strip(),
                        pd.to_numeric(fd_visible_field["Captain/MVP Ownership %"], errors="coerce")
                    ))
                    fd_mvp = fd_names_for_field.map(fd_mvp_map).fillna(0.0)
                else:
                    fd_mvp = pd.Series(0.0, index=fd_player_display.index)
                fd_player_display["Field MVP Own %"] = fd_mvp.round(1)
                fd_player_display["Field FLEX Own %"] = (fd_overall.fillna(0.0) - fd_mvp).clip(lower=0.0).round(1)
                fd_player_display = fd_player_display.drop(columns=["Field Own %"], errors="ignore")
            else:
                fd_player_display["Field Own %"] = fd_overall.round(1)
                fd_player_display = fd_player_display.drop(columns=["Field MVP Own %", "Field FLEX Own %"], errors="ignore")
        else:
            if lineup_mode == "Single Game":
                fd_player_display["Field MVP Own %"] = np.nan
                fd_player_display["Field FLEX Own %"] = np.nan
                fd_player_display = fd_player_display.drop(columns=["Field Own %"], errors="ignore")
            else:
                fd_player_display["Field Own %"] = np.nan
                fd_player_display = fd_player_display.drop(columns=["Field MVP Own %", "Field FLEX Own %"], errors="ignore")

        from simmah_player_display import complete_player_display
        _fd_mode = lineup_mode.replace(" ", "_").lower()
        fd_player_display = complete_player_display(
            fd_player_display,
            st.session_state.get("fd_simulation_df_" + _fd_mode),
            st.session_state.get("fd_assigned_display_" + _fd_mode, st.session_state.get(fd_build_key)),
            st.session_state.get("fd_contest_field_" + _fd_mode),
        )
        from simmah_leverage import attach_leverage
        fd_player_display = attach_leverage(fd_player_display, leverage_opportunities_cached(
            st.session_state.get("fd_simulation_df_" + _fd_mode),
            st.session_state.get(fd_build_key)))
        st.caption("Leverage (pp) = candidate-best selection share minus projected ownership, or simulated-field ownership when projections are unavailable. Positive values suggest underownership within this candidate set, not guaranteed profit. CPT/MVP and FLEX leverage use separate simulated-field ownership. Values fill after SIM, BUILD and field generation.")
        st.caption("Simulation and ownership summaries fill after SIM completes. Pending values are not zero; external ownership and weather require available source data.")
        from simmah_leverage import add_value_columns
        fd_player_display = add_value_columns(fd_player_display)
        fd_snapshot_display = fd_player_display.copy()
        for sim_key, sim_label in [
            ("Mean", "Sim Pts"), ("P10", "Sim P10"), ("P25", "Sim P25"),
            ("P50", "Sim P50"), ("P75", "Sim P75"), ("P90", "Sim P90"),
            ("P95", "Sim P95"), ("P99", "Sim P99"),
        ]:
            fd_snapshot_display[sim_label] = fd_snapshot_display["Name"].astype(str).map(
                lambda name, key=sim_key: pd.to_numeric(player_sim.get(str(name), {}).get(key), errors="coerce")
            )
        ownership_by_format = st.session_state.get("latest_field_ownership_by_format", {})
        fd_field_ownership = ownership_by_format.get(selected_format) if isinstance(ownership_by_format, dict) else None
        if isinstance(fd_field_ownership, pd.DataFrame) and not fd_field_ownership.empty:
            own_map = dict(zip(
                fd_field_ownership["Name"].astype(str).str.strip(),
                pd.to_numeric(fd_field_ownership["Ownership %"], errors="coerce"),
            ))
            fd_snapshot_display["Field Own %"] = fd_snapshot_display["Name"].astype(str).str.strip().map(own_map)
            if "Captain/MVP Ownership %" in fd_field_ownership.columns:
                mvp_map = dict(zip(
                    fd_field_ownership["Name"].astype(str).str.strip(),
                    pd.to_numeric(fd_field_ownership["Captain/MVP Ownership %"], errors="coerce"),
                ))
                fd_snapshot_display["Field MVP Own %"] = fd_snapshot_display["Name"].astype(str).str.strip().map(mvp_map)
        if st.session_state.get("fd_simulation_ready_" + lineup_mode.replace(" ", "_").lower()):
            save_automatic_pregame_snapshot(
                fd_snapshot_display,
                selected_format,
                correlation_pct=float(correlation_strength) * 100.0,
                aggressiveness_pct=float(aggressiveness) * 100.0,
            )

        if lineup_mode == "Full Roster":
            _fd_classic_order = [
                "Fade", "Lock", "Name", "Team", "Opponent", "Position", "Salary", "Injury Status",
                "Projection", "Sim Pts", "Exposure %", "Field Own %", "Min Exposure %", "Max Exposure %",
                "ProjectionSource", "Sim P10", "Sim P25", "Sim P50", "Sim P75", "Sim P90", "Sim P95",
                "Sim P99", "Cap Hit %"
            ]
            fd_player_display = fd_player_display[
                [c for c in _fd_classic_order if c in fd_player_display.columns]
                + [c for c in fd_player_display.columns if c not in _fd_classic_order]
            ]
        # Let the user override injury status directly in the FanDuel Player Pool.
        _fd_manual_injury_key = "fd_manual_injury_status_" + lineup_mode.replace(" ", "_").lower()
        _fd_manual_injuries = st.session_state.get(_fd_manual_injury_key, {})
        if not isinstance(_fd_manual_injuries, dict):
            _fd_manual_injuries = {}
        if "Injury Status" in fd_player_display.columns:
            fd_player_display["Injury Status"] = fd_player_display.apply(
                lambda row: _fd_manual_injuries.get(str(row.get("Name", "")), row.get("Injury Status", "Active")), axis=1
            )
        _fd_show_all_columns = st.checkbox("Show all player columns", value=False,
            key="fd_show_all_player_columns_" + lineup_mode.replace(" ", "_").lower())
        fd_player_display = injury_player_pool(fd_player_display)
        _fd_edited_pool = st.data_editor(
            fd_player_display,
            use_container_width=True,
            hide_index=True,
            column_order=None if _fd_show_all_columns else player_columns(fd_player_display),
            row_height=32,
            height=660,
            disabled=[c for c in fd_player_display.columns if c not in {"Fade", "Lock", "Injury Status", "Min Exposure %", "Max Exposure %"}],
            column_config={
                **player_column_config(st),
                "Name": st.column_config.TextColumn("Name"),
                "Player": st.column_config.TextColumn("Player", pinned=True),
                "Injury Status": st.column_config.SelectboxColumn("Injury Status", options=["Active", "Questionable", "Doubtful", "Out"], required=True),
            },
            key="fd_player_pool_editor_" + lineup_mode.replace(" ", "_").lower(),
        )
        if isinstance(_fd_edited_pool, pd.DataFrame) and "Injury Status" in _fd_edited_pool.columns:
            _fd_auto_status = dict(zip(fd_player_display["Name"].astype(str), fd_player_display["Injury Status"].astype(str)))
            _fd_new_manual = dict(_fd_manual_injuries)
            for _fd_name, _fd_status in zip(_fd_edited_pool["Name"].astype(str), _fd_edited_pool["Injury Status"].astype(str)):
                if _fd_status != _fd_auto_status.get(_fd_name):
                    _fd_new_manual[_fd_name] = _fd_status
            if _fd_new_manual != _fd_manual_injuries:
                st.session_state[_fd_manual_injury_key] = _fd_new_manual
                workspace_rerun(st, _loaded_slate_tabs)
            fd_players["Injury Status"] = fd_players.apply(
                lambda row: _fd_new_manual.get(str(row.get("Name", "")), row.get("Injury Status", "Active")), axis=1
            )
            fd_players = fd_players[~fd_players["Injury Status"].astype(str).str.casefold().eq("out")].copy()
        fd_player_display = _fd_edited_pool.copy() if isinstance(_fd_edited_pool, pd.DataFrame) else fd_player_display
        _fd_scoring_download_slot = st.empty()



        fd_players = apply_game_weather_context(fd_players, fd_raw)

    with _tab_build:
        render_saved_market_calibration(platform, lineup_mode, fd_players)
        with _build_controls:
            st.write("### Build Settings")
        _build_controls.caption("The 5,000-lineup build automatically spreads player exposure while still favoring stronger simulated scores.")
        build_cols = [_build_controls.container() for _ in range(2)]
        with build_cols[0]:
            fd_salary_range = st.slider(
                "Allowed lineup salary range",
                min_value=0,
                max_value=60000,
                value=(58000, 60000) if lineup_mode == "Full Roster" else (54000, 60000),
                step=100,
                format="$%d",
                key="fd_build_salary_range_" + lineup_mode.replace(" ", "_").lower() + ("_58000" if lineup_mode == "Full Roster" else ""),
                help="Only build lineups whose total salary falls inside this range."
            )
        with build_cols[1]:
            portfolio_diversity, aggressiveness = render_diversity_controls(st, platform, lineup_mode, SIMULATION_COUNT)
            if lineup_mode in ("Showdown", "Single Game"):
                correlation_pct = st.slider(
                    "Game Correlation", 0, 100,
                    0 if ((platform == "DraftKings" and lineup_mode == "Showdown") or (platform == "FanDuel" and lineup_mode == "Single Game")) else 70,
                    step=5,
                    help="Controls how strongly shared game conditions connect player outcomes.",
                    key=f"single_game_correlation_strength_{platform}_{lineup_mode}",
                )
                correlation_strength = correlation_pct / 100.0
            else:
                correlation_strength = 1.0
            st.session_state["active_game_correlation_strength"] = correlation_strength
        with _build_controls:
            if lineup_mode == "Full Roster":
                fd_stack_rules = st.multiselect(
                    "Stacks to use in MY lineups",
                    BUILD_STACK_OPTIONS,
                    default=[ANY_STACK_OPTION],
                    key="fd_full_roster_stack_rules_v2",
                    help="Any / All allows every primary structure, including unstacked lineups, and takes precedence over other primary choices. No stack requires zero same-team WR/TE with your QB. Otherwise, accept any selected structure. Optional secondary rules still apply. Clear selections also allows any structure.",
                )
                fd_secondary_stack_rules = st.multiselect(
                    "Optional secondary stacks",
                    SECONDARY_STACK_OPTIONS,
                    default=[],
                    key="fd_full_roster_stack_rules_secondary_v2",
                    help="Each selected secondary rule is required in addition to a selected QB stack. Mini-stacks use another game.",
                )
                st.caption("Choose your FanDuel Full Roster stack rules before pressing BUILD.")

        _build_controls.write("### Run")
        _fd_run_center = _build_controls.container()
        with _fd_run_center:
            fd_sim_button = st.button(
                "Run Build",
                type="primary",
                use_container_width=True,
                key="fd_sim_" + lineup_mode.replace(" ", "_").lower(),
                help="Runs player simulations, builds your lineups, builds the opponent field, and runs the contest comparison."
            )
        fd_run_all_clicked = fd_sim_button
        fd_sim_clicked = fd_sim_button
        fd_build_clicked = fd_sim_button
        fd_contest_clicked = fd_sim_button
        fd_workflow_status = None
        if fd_run_all_clicked:
            fd_workflow_status = st.empty()
            fd_workflow_status.info(
                f"Step 1 of 4: Running {SIMULATION_COUNT:,} player simulations for FanDuel {lineup_mode}..."
            )
        if fd_sim_clicked:
            with st.spinner(f"Running {SIMULATION_COUNT:,} shared historical/PBP simulations for FanDuel..."):
                rng = np.random.default_rng()
                simulated_scores = simulate_fd_play_by_play(fd_players, rng, SIMULATION_COUNT, correlation_strength)
                player_sim = {}
                for sim_name in fd_players["Name"].astype(str):
                    if sim_name not in simulated_scores.columns:
                        continue
                    values = pd.to_numeric(simulated_scores[sim_name], errors="coerce").dropna().to_numpy(dtype=float)
                    if not len(values):
                        continue
                    player_sim[sim_name] = {
                        "Mean": float(np.mean(values)),
                        "P10": float(np.quantile(values, 0.10)),
                        "P25": float(np.quantile(values, 0.25)),
                        "P50": float(np.quantile(values, 0.50)),
                        "P75": float(np.quantile(values, 0.75)),
                        "P90": float(np.quantile(values, 0.90)),
                        "P95": float(np.quantile(values, 0.95)),
                        "P99": float(np.quantile(values, 0.99)),
                        "StdDev": float(np.std(values)),
                    }
                _fd_mode_key = lineup_mode.replace(" ", "_").lower()
                st.session_state["fd_player_sim_" + _fd_mode_key] = player_sim
                st.session_state["fd_simulation_df_" + _fd_mode_key] = simulated_scores.copy()
                # Cap Hit % = share of simulated game outcomes in which the player
                # finishes tied for the highest raw FanDuel score on the slate.
                # Split tied top outcomes evenly so the percentages remain meaningful.
                _fd_scores = simulated_scores.apply(pd.to_numeric, errors="coerce").fillna(0.0)
                _fd_row_max = _fd_scores.max(axis=1)
                _fd_top_mask = _fd_scores.eq(_fd_row_max, axis=0)
                _fd_tie_count = _fd_top_mask.sum(axis=1).clip(lower=1)
                _fd_cap_hits = {
                    str(_fd_name): float(100.0 * (_fd_top_mask[_fd_name] / _fd_tie_count).mean())
                    for _fd_name in _fd_scores.columns
                }
                st.session_state["fd_simulation_cap_hit_pct_" + _fd_mode_key] = _fd_cap_hits
                st.session_state["fd_simulation_ready_" + _fd_mode_key] = True
                # Keep the already-created Player Pool dataframe wired to THIS run's
                # play-by-play output. On the next normal rerun the same values are
                # restored from session state before the table is drawn.
                if "fd_player_display" in locals() and isinstance(fd_player_display, pd.DataFrame):
                    for _sim_key, _sim_label in [
                        ("Mean", "Sim Pts"), ("P10", "Sim P10"), ("P25", "Sim P25"),
                        ("P50", "Sim P50"), ("P75", "Sim P75"), ("P90", "Sim P90"),
                        ("P95", "Sim P95"), ("P99", "Sim P99"),
                    ]:
                        fd_player_display[_sim_label] = fd_player_display["Name"].astype(str).map(
                            lambda _name, _key=_sim_key: pd.to_numeric(player_sim.get(str(_name), {}).get(_key), errors="coerce")
                        )
            if fd_run_all_clicked:
                fd_workflow_status.info(
                    "Step 2 of 4: Preparing rankings and building your candidate lineups..."
                )

        # Exposure/ranking changes reuse this upload's candidates and simulations.
        # Live projection values and dataframe ordering are not slate identity.
        fd_signature = uploaded_slate_signature(fd_slate_file, "FanDuel", lineup_mode)
        if "fd_saved_builds" not in st.session_state:
            st.session_state["fd_saved_builds"] = {}
        fd_build_key = "fd_lineups_" + lineup_mode.replace(" ", "_").lower()
        fd_active_key = "fd_active_signature_" + lineup_mode.replace(" ", "_").lower()
        previous_fd_signature = st.session_state.get(fd_active_key)
        if signature_matches_upload(previous_fd_signature, fd_signature, fd_players[["Name", "Position", "Team", "Salary"]].astype(str).itertuples(index=False, name=None)):
            st.session_state[fd_active_key] = fd_signature
        else:
            if previous_fd_signature is not None and fd_build_key in st.session_state:
                st.session_state["fd_saved_builds"][previous_fd_signature] = {
                    "lineups": st.session_state[fd_build_key]
                }
            st.session_state.pop(fd_build_key, None)
            fd_saved = st.session_state["fd_saved_builds"].get(fd_signature, {})
            if "lineups" in fd_saved:
                st.session_state[fd_build_key] = fd_saved["lineups"]
            st.session_state[fd_active_key] = fd_signature

        if lineup_mode == "Single Game":
            st.caption(
                "FanDuel Single Game: 1 MVP (1.5x points and salary) plus 5 FLEX players. "
                "Salary cap: $60,000."
            )
            fd_slots = ["MVP", "FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5"]
        else:
            st.caption(
                "FanDuel NFL Full Roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), D. "
                "Salary cap: $60,000."
            )
            fd_slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "D"]

        # Preserve the Full Roster stack selection made above. Single Game has no stack rules.
        if lineup_mode != "Full Roster":
            fd_stack_rules = []
            fd_secondary_stack_rules = []
        if fd_build_clicked:
            st.session_state.pop(fd_build_key, None)
            st.session_state.pop("fd_contest_field_" + lineup_mode.replace(" ", "_").lower(), None)
            st.session_state.pop("fd_contest_field_ready_" + lineup_mode.replace(" ", "_").lower(), None)
            st.session_state.pop("fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower(), None)
            pool = fd_players.drop_duplicates("Name", keep="first").reset_index(drop=True)
            if lineup_mode == "Single Game":
                roster = [("MVP", set())] + [(f"FLEX{i}", set()) for i in range(1, 6)]
            else:
                roster = [("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                          ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                          ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}), ("D", {"D", "DST", "DEF"})]
            slots = [slot for slot, _ in roster]
            try:
                fd_results = build_joint_candidate_pool(pool, "FanDuel", lineup_mode,
                    st.session_state["fd_simulation_df_" + lineup_mode.replace(" ", "_").lower()], roster,
                    int(fd_salary_range[0]), min(int(fd_salary_range[1]), 60000),
                    selected_stacks=fd_stack_rules, secondary_stacks=fd_secondary_stack_rules,
                    aggressiveness=aggressiveness)
                st.session_state[fd_build_key] = fd_results
                st.session_state["fd_saved_builds"][fd_signature] = {"lineups": fd_results}
                if fd_run_all_clicked:
                    fd_workflow_status.info("Step 3 of 4: Building the simulated opponent field...")
            except Exception as exc:
                st.error(f"FanDuel candidate build stopped: {exc}")
                workspace_stop(st, _loaded_slate_tabs)

        if fd_contest_clicked:
            fd_pool = fd_players.copy()
            fd_pool["Eligible"] = fd_pool["Position"].apply(
                lambda value: set(str(value).upper().replace(" ", "").split("/"))
            )
            # This is already the filtered FanDuel pool. Never apply a shared
            # DraftKings available_players list to FanDuel contest opponents.
            fd_pool["Projection"] = pd.to_numeric(fd_pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01)
            # Use this FanDuel mode's own PBP outcomes. The shared simulation_df key
            # belongs to the DraftKings workflow and must never drive FanDuel opponents.
            _fd_mode_key = lineup_mode.replace(" ", "_").lower()
            fd_sim_df = st.session_state.get("fd_simulation_df_" + _fd_mode_key)
            if isinstance(fd_sim_df, pd.DataFrame) and not fd_sim_df.empty:
                fd_mean_scores = fd_sim_df.mean(axis=0).to_dict()
            else:
                fd_mean_scores = {
                    str(name): float(values.get("Mean", 0.0))
                    for name, values in player_sim.items()
                    if isinstance(values, dict)
                }
            fd_pool["MeanPoints"] = fd_pool["Name"].map(fd_mean_scores).fillna(fd_pool["Projection"])
            if lineup_mode == "Full Roster":
                fd_pool = attach_main_slate_ownership(fd_pool, "fanduel")
                own_cols = [c for c in ["Name", "Team", "Position", "Projected Ownership", "Ownership Selection Weight", "Ownership Source", "Ownership Updated UTC", "Ownership Week"] if c in fd_pool.columns]
                st.session_state["fd_full_ownership_snapshot"] = fd_pool[own_cols].copy()
                with st.expander("Opponent projected ownership inputs", expanded=False):
                    st.dataframe(injury_frame(st, fd_pool[own_cols]), use_container_width=True, hide_index=True)
                    st.download_button("DOWNLOAD OWNERSHIP SNAPSHOT", fd_pool[own_cols].to_csv(index=False).encode("utf-8"), "FanDuel_Full_Ownership_Snapshot.csv", "text/csv", key="fd_full_ownership_snapshot_download", on_click="ignore")
            fd_weights = opponent_field_selection_weights(
                fd_pool, fd_pool["MeanPoints"].to_numpy(dtype=float)
            )
            fd_weights = fd_weights / fd_weights.sum() if fd_weights.sum() else np.full(len(fd_pool), 1 / max(len(fd_pool), 1))

            # FanDuel Single Game role weights: MVP and FLEX are modeled separately.
            # This mirrors the DraftKings Showdown approach: overall ownership drives
            # field selection, while special-role ownership drives the MVP/CPT slot.
            fd_role_lookup = {str(c).strip().casefold(): c for c in fd_pool.columns}
            fd_mvp_col = next((fd_role_lookup[k] for k in (
                "field mvp own %", "mvp ownership %", "projected mvp ownership",
                "captain/mvp ownership %", "mvp own %"
            ) if k in fd_role_lookup), None)
            fd_flex_col = next((fd_role_lookup[k] for k in (
                "field flex own %", "flex ownership %", "projected flex ownership",
                "flex own %"
            ) if k in fd_role_lookup), None)

            if fd_mvp_col is not None:
                fd_mvp_weights = pd.to_numeric(fd_pool[fd_mvp_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
                if fd_mvp_weights.sum() <= 0:
                    fd_mvp_weights = fd_weights.copy()
            else:
                fd_mvp_weights = fd_weights.copy()

            if fd_flex_col is not None:
                fd_flex_weights = pd.to_numeric(fd_pool[fd_flex_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
                if fd_flex_weights.sum() <= 0:
                    fd_flex_weights = fd_weights.copy()
            else:
                fd_flex_weights = fd_weights.copy()

            rng = np.random.default_rng(123)
            opponent_rows = []
            seen_opponents = set()
            attempts = 0
            if len(fd_pool) < len(fd_slots):
                st.error(f"At least {len(fd_slots)} eligible players are required for FanDuel Contest Sim.")
            else:
                if fd_opponent_target <= 0:
                    st.warning("Total contest entries must be greater than your own entries.")
                fd_field_progress = st.progress(
                    0,
                    text=f"Building FanDuel opponent field: 0 / {fd_opponent_target:,}"
                )
                _fd_generation_target = learned_field_proposal_target("FanDuel", lineup_mode, st.session_state.get("selected_fd_contest", {}), len(fd_slots), ownership_proposal_target(fd_pool, lineup_mode, fd_opponent_target), fd_pool)
                with st.spinner(f"Building {_fd_generation_target:,} simulated FanDuel contest entries..."):
                    if lineup_mode == "Full Roster":
                        from simmah_classic_field import build_full_roster_field
                        _fd_salary_counts = None
                        _fd_team_count = fd_pool["Team"].dropna().nunique()
                        if _fd_team_count >= 16:
                            import json as _fd_history_json
                            _fd_salary_path = Path(__file__).resolve().parent / "data" / "fd_full_salary_history.json"
                            if _fd_salary_path.exists():
                                _fd_salary_history = _fd_history_json.loads(_fd_salary_path.read_text())
                                _fd_salary_counts = _fd_salary_history["salary_counts"]
                        _fd_batched_field = build_full_roster_field(fd_pool, fd_weights, fd_slots, _fd_generation_target,
                            rng=rng, progress=lambda fraction,text: fd_field_progress.progress(fraction,text=text),
                            salary_counts=_fd_salary_counts, construction_distribution=opponent_construction_distribution(
                                "FanDuel", "Full Roster", st.session_state.get("selected_fd_contest", {}), fd_pool))
                        if _fd_salary_counts:
                            st.caption("Opponent salary usage uses completed 11-game FD history, conditioned on the supported $59,000–$60,000 range. Ownership and duplicate rates remain estimates.")

                        opponent_rows = _fd_batched_field.to_dict("records")
                    else:
                        from simmah_single_field import build_fanduel_single_field
                        _fd_single_field = build_fanduel_single_field(
                            fd_pool, fd_mvp_weights, fd_flex_weights, _fd_generation_target,
                            fd_salary_range, rng=rng,
                            progress=lambda fraction,text: fd_field_progress.progress(fraction,text=text),
                        )
                        opponent_rows = _fd_single_field.to_dict("records")
                fd_field_progress.empty()
                _fd_field_input = pd.DataFrame(opponent_rows)
                if lineup_mode == "Full Roster":
                    _fd_field_input.attrs.update(_fd_batched_field.attrs)
                opponent_df = apply_learned_field(_fd_field_input, fd_pool, fd_slots, "FanDuel", lineup_mode,
                    st.session_state.get("selected_fd_contest", {}), fd_opponent_target, rng)
                st.session_state["fd_contest_field_" + lineup_mode.replace(" ", "_").lower()] = opponent_df
                st.session_state["fd_contest_field_ready_" + lineup_mode.replace(" ", "_").lower()] = not opponent_df.empty
                if not opponent_df.empty:
                    show_field_ownership(opponent_df, fd_slots, "Simulated FanDuel Player Ownership", captain_slot=("MVP" if lineup_mode == "Single Game" else None))
                    st.success(f"Created {len(opponent_df):,} simulated FanDuel opponent lineups.")
                    # FanDuel Full Roster sanity diagnostics: show field construction
                    # strength on every SIM so weak-field problems are visible before
                    # trusting finish rates or ROI. FanDuel-only; DraftKings is untouched.
                    if lineup_mode == "Full Roster":
                        _fd_sanity_user = st.session_state.get(fd_build_key)
                        _fd_field_proj = pd.to_numeric(opponent_df.get("ProjectedPoints"), errors="coerce").dropna()
                        _fd_field_salary = pd.to_numeric(opponent_df.get("Salary"), errors="coerce").dropna()
                        _fd_user_proj = (
                            pd.to_numeric(_fd_sanity_user.get("ProjectedPoints"), errors="coerce").dropna()
                            if isinstance(_fd_sanity_user, pd.DataFrame) and not _fd_sanity_user.empty
                            else pd.Series(dtype=float)
                        )
                        _fd_user_salary = (
                            pd.to_numeric(_fd_sanity_user.get("Salary"), errors="coerce").dropna()
                            if isinstance(_fd_sanity_user, pd.DataFrame) and not _fd_sanity_user.empty
                            else pd.Series(dtype=float)
                        )
                        st.write("### FanDuel Full Roster Field Sanity Check")
                        _fd_sanity_cols = st.columns(4)
                        _fd_sanity_cols[0].metric(
                            "Opponent avg projection",
                            f"{_fd_field_proj.mean():.2f}" if not _fd_field_proj.empty else "N/A",
                        )
                        _fd_sanity_cols[1].metric(
                            "My avg projection",
                            f"{_fd_user_proj.mean():.2f}" if not _fd_user_proj.empty else "N/A",
                        )
                        _fd_sanity_cols[2].metric(
                            "Opponent avg salary",
                            f"${_fd_field_salary.mean():,.0f}" if not _fd_field_salary.empty else "N/A",
                        )
                        _fd_sanity_cols[3].metric(
                            "My avg salary",
                            f"${_fd_user_salary.mean():,.0f}" if not _fd_user_salary.empty else "N/A",
                        )
                        if not _fd_field_proj.empty:
                            _fd_q = _fd_field_proj.quantile([0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
                            _fd_sanity_table = pd.DataFrame({
                                "Field metric": ["P10", "P25", "P50", "P75", "P90", "P95", "P99"],
                                "Projected points": [float(_fd_q.loc[q]) for q in [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]],
                            })
                            st.dataframe(injury_frame(st, _fd_sanity_table), use_container_width=True, hide_index=True)
                            if not _fd_user_proj.empty:
                                _fd_user_vs_field = float(np.mean([
                                    np.mean(_fd_field_proj.to_numpy(dtype=float) <= score)
                                    for score in _fd_user_proj.to_numpy(dtype=float)
                                ]))
                                st.caption(
                                    f"Projection-only diagnostic: your generated lineups average the "
                                    f"{100.0 * _fd_user_vs_field:.1f}th percentile versus the simulated opponent field. "
                                    "This is not ROI; it isolates field-construction strength."
                                )
                        if not _fd_field_salary.empty:
                            _fd_near_cap = float((_fd_field_salary >= 59000).mean()) * 100.0
                            _fd_floor = float((_fd_field_salary >= 57000).mean()) * 100.0
                            st.caption(
                                f"Opponent salary usage: {_fd_near_cap:.1f}% use at least $59,000; "
                                f"{_fd_floor:.1f}% use at least $57,000."
                            )
                    fd_contest_details = st.session_state.get("selected_fd_contest")
                    if fd_contest_details:
                        st.info(
                            f"Contest selected from your FanDuel entry CSV: {fd_contest_details['name']} "
                            f"(ID {fd_contest_details['id']}). Your file has "
                            f"{fd_contest_details['your_entries']} entries in this contest. "
                            "The opponent field is simulated."
                        )
                    if fd_run_all_clicked:
                        fd_workflow_status.info("Step 4 of 4: Scoring your lineups against the contest field...")
                    fd_step4_status = st.empty()
                    fd_step4_status.info("Step 4 of 4: Scoring your lineups against the contest field...")
                    fd_step4_progress = st.progress(0, text="Step 4 of 4: Preparing FanDuel contest comparison...")
                    user_lineups = st.session_state.get(fd_build_key)
                    if user_lineups is None or user_lineups.empty:
                        fd_step4_status.error("Step 4 could not run because the current SIM did not produce user lineups.")
                        fd_step4_progress.empty()
                        st.warning("SIM is running the lineup build and contest comparison together.")
                    else:
                        scores = opponent_df["ProjectedPoints"].to_numpy(dtype=float)
                        compared = add_lineup_field_ownership(user_lineups.copy())
                        if lineup_mode == "Full Roster":
                            from simmah_contests import evaluate_contest
                            _fd_final_field = opponent_df
                            _fd_spec = full_roster_contest_parameters(st.session_state.get("selected_fd_contest"), len(_fd_final_field))
                            _fd_roi_sim = st.session_state.get("fd_simulation_df_full_roster")
                            if not isinstance(_fd_roi_sim, pd.DataFrame) or len(_fd_roi_sim) != SIMULATION_COUNT:
                                raise ValueError("Run a fresh SIM before evaluating FanDuel Full Roster")
                            compared = evaluate_contest(_fd_roi_sim, compared, _fd_final_field, fd_slots,
                                _fd_spec["field_size"], _fd_spec["tiers"], _fd_spec["fee"],
                                progress=lambda fraction,text: fd_step4_progress.progress(fraction,text=text))
                            if not _fd_spec["payouts_known"]:
                                compared = compared.drop(columns=["CashRate", "Expected Prize ($)", "Expected Net ($)", "Expected ROI (%)", "Entry Fee ($)"], errors="ignore")
                                compared["ContestScore"] = compared["Top1"]
                                st.info("Payouts or contest size are unavailable: finish rates use an estimated field; cash and ROI remain pending.")
                            st.session_state["fd_full_roster_evaluation_context"] = dict(st.session_state.get("selected_fd_contest") or {})
                            st.caption(f"All {len(_fd_roi_sim):,} independent evaluation outcomes scored against the same {len(_fd_final_field):,} opponents. Ties share occupied prizes; no extra ROI field is built.")
                        else:
                            from simmah_contests import evaluate_contest
                            _single_outcomes = st.session_state.get("fd_simulation_df_single_game")
                            if not isinstance(_single_outcomes, pd.DataFrame) or len(_single_outcomes) != SIMULATION_COUNT:
                                raise ValueError("Run a fresh Single Game SIM before contest evaluation")
                            _single_spec = full_roster_contest_parameters(st.session_state.get("selected_fd_contest"), len(opponent_df))
                            compared = evaluate_contest(_single_outcomes, compared, opponent_df, fd_slots,
                                _single_spec["field_size"], _single_spec["tiers"], _single_spec["fee"],
                                multipliers=[1.5, 1, 1, 1, 1, 1],
                                progress=lambda fraction,text: fd_step4_progress.progress(fraction,text=text))
                            if not _single_spec["payouts_known"]:
                                compared = compared.drop(columns=["CashRate", "Expected Prize ($)", "Expected Net ($)", "Expected ROI (%)", "Entry Fee ($)"], errors="ignore")
                                compared["ContestScore"] = compared["Top1"]
                            st.session_state["fd_single_game_evaluation_context"] = dict(st.session_state.get("selected_fd_contest") or {})
                            st.session_state["fd_single_game_evaluation_engine"] = "shared-contest-mvp-v1"
                            st.caption("Candidates and opponents scored on the same independent game outcomes, including 1.5x MVP points. Cash and ROI require confirmed contest payouts.")
                        st.session_state["fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()] = compared
                        fd_step4_progress.progress(1.0, text="Step 4 of 4 complete: FanDuel contest comparison finished.")
                        fd_step4_status.success("Step 4 of 4 complete: contest comparison finished.")
                        st.write("### FanDuel Lineups vs. Simulated Contest Field")
                        st.dataframe(injury_frame(st, compared), use_container_width=True, hide_index=True)
                        if all(c in compared.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                            _fd_sanity = pd.DataFrame([{
                                "Top 1%": round(100 * float(compared["Top1"].mean()), 2),
                                "Top 5%": round(100 * float(compared["Top5"].mean()), 2),
                                "Top 10%": round(100 * float(compared["Top10"].mean()), 2),
                                "Cash %": round(100 * float(compared["CashRate"].mean()), 2),
                            }])
                            st.write("### Field Sanity Check")
                            st.dataframe(injury_frame(st, _fd_sanity), use_container_width=True, hide_index=True)
                        # Keep the contest results area consistent with DraftKings Classic and Showdown.
                else:
                    st.error("Could not create valid FanDuel opponent lineups. Check the player pool and salary range.")
            if fd_run_all_clicked:
                _fd_step4_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()
                _fd_step4_result = st.session_state.get(_fd_step4_key)
                if isinstance(_fd_step4_result, pd.DataFrame) and not _fd_step4_result.empty:
                    # The Player Pool and its download widgets were created earlier in
                    # this Streamlit run, before Step 1 replaced the projection fallback
                    # with real PBP outcomes. Rerun once now so the visible/exported
                    # P10-P99 values are rebuilt from fd_player_sim_* session state.
                    st.session_state["fd_last_completed_workflow_" + lineup_mode.replace(" ", "_").lower()] = True
                    fd_workflow_status.success("FanDuel SIM complete. Refreshing the Player Pool with the new PBP results...")
                    # The Player Pool and export were rendered before this SIM click.
                    # Rerun once so they are rebuilt from the fd_player_sim_* values
                    # saved above instead of the pre-SIM projection placeholders.
                    workspace_rerun(st, _loaded_slate_tabs)
                else:
                    fd_workflow_status.error("FanDuel SIM stopped before Step 4 produced a contest comparison.")

        fd_results = st.session_state.get(fd_build_key)
        if fd_results is not None:
            _fd_eligible_now = set(fd_players["Name"].astype(str))
            fd_results = fd_results.loc[fd_results[fd_slots].isin(_fd_eligible_now).all(axis=1)].copy()
            if fd_results.empty:
                st.warning("No saved candidates remain eligible after player-pool changes. Run Build to generate new candidates.")
                workspace_stop(st, _loaded_slate_tabs)
            fd_results = remove_out_players_from_lineups(fd_results, fd_slots, "FanDuel")
            st.session_state[fd_build_key] = fd_results
            st.divider()
            st.write("## Portfolio")
            st.caption(f"{len(fd_results):,} candidate lineups available. Rank the pool, review your assigned entries, then export.")

            # Use the same ranking choices as DraftKings Showdown for both FanDuel formats.
            fd_comparison_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()
            fd_rank_source = st.session_state.get(fd_comparison_key)
            if isinstance(fd_rank_source, pd.DataFrame) and all(slot in fd_rank_source for slot in fd_slots):
                fd_rank_source = fd_rank_source.loc[fd_rank_source[fd_slots].isin(_fd_eligible_now).all(axis=1)].copy()
            if lineup_mode == "Full Roster" and st.session_state.get("fd_full_roster_evaluation_context") != dict(st.session_state.get("selected_fd_contest") or {}):
                fd_rank_source = None

            if lineup_mode == "Single Game" and (st.session_state.get("fd_single_game_evaluation_engine") != "shared-contest-mvp-v1" or st.session_state.get("fd_single_game_evaluation_context") != dict(st.session_state.get("selected_fd_contest") or {})):
                fd_rank_source = None
                st.warning("Run a fresh Single Game SIM to calculate shared-outcome finish rates.")
            render_value_leverage_finder(fd_player_display, fd_rank_source,
                st.session_state.get("fd_contest_field_" + lineup_mode.replace(" ", "_").lower()),
                fd_slots, "fd_" + lineup_mode, "MVP" if lineup_mode == "Single Game" else None)
            if not isinstance(fd_rank_source, pd.DataFrame) or fd_rank_source.empty:
                fd_rank_source = add_field_ranking_metrics(fd_results, fd_results["ProjectedPoints"].to_numpy(dtype=float))
            # Persistent FanDuel Full Roster sanity check and opponent lineup viewer.
            # Read from session state so these remain visible after SIM triggers workspace_rerun(st, _loaded_slate_tabs).
            if lineup_mode in {"Full Roster", "Single Game"}:
                _fd_field_key = "fd_contest_field_" + lineup_mode.replace(" ", "_").lower()
                _fd_persist_field = st.session_state.get(_fd_field_key)
                if isinstance(_fd_persist_field, pd.DataFrame) and not _fd_persist_field.empty:
                    _fd_field_proj = pd.to_numeric(_fd_persist_field.get("ProjectedPoints"), errors="coerce").dropna()
                    _fd_field_salary = pd.to_numeric(_fd_persist_field.get("Salary"), errors="coerce").dropna()
                    _fd_my_proj = pd.to_numeric(fd_rank_source.get("ProjectedPoints"), errors="coerce").dropna()
                    _fd_my_salary = pd.to_numeric(fd_rank_source.get("Salary"), errors="coerce").dropna()

                    st.write("### Opponent Field")
                    st.caption(f"FanDuel {lineup_mode}: {len(_fd_persist_field):,} simulated entries.")
                    st.download_button(
                        "DOWNLOAD OPPONENT FIELD", _fd_persist_field.to_csv(index=False).encode("utf-8"),
                        "fanduel_" + lineup_mode.replace(" ", "_").lower() + "_opponent_field.csv",
                        "text/csv", key="fd_opponent_field_visible_" + lineup_mode.replace(" ", "_").lower(),
                        on_click="ignore", use_container_width=True,
                    )
                    _fd_sc = st.columns(4)
                    _fd_sc[0].metric("Opponent avg projection", f"{_fd_field_proj.mean():.2f}" if not _fd_field_proj.empty else "N/A")
                    _fd_sc[1].metric("My avg projection", f"{_fd_my_proj.mean():.2f}" if not _fd_my_proj.empty else "N/A")
                    _fd_sc[2].metric("Opponent avg salary", f"${_fd_field_salary.mean():,.0f}" if not _fd_field_salary.empty else "N/A")
                    _fd_sc[3].metric("My avg salary", f"${_fd_my_salary.mean():,.0f}" if not _fd_my_salary.empty else "N/A")

                    if not _fd_field_proj.empty:
                        _fd_q_levels = [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
                        _fd_q = _fd_field_proj.quantile(_fd_q_levels)
                        st.dataframe(injury_frame(st, pd.DataFrame({
                            "Opponent field": ["P10", "P25", "P50", "P75", "P90", "P95", "P99"],
                            "Projected points": [round(float(_fd_q.loc[q]), 2) for q in _fd_q_levels],
                        })), use_container_width=True, hide_index=True)
                        if not _fd_my_proj.empty:
                            _fd_field_values = _fd_field_proj.to_numpy(dtype=float)
                            _fd_my_percentiles = [float(np.mean(_fd_field_values <= x)) for x in _fd_my_proj.to_numpy(dtype=float)]
                            st.caption(
                                f"Projection-only diagnostic: your generated lineup pool averages the "
                                f"{100.0 * float(np.mean(_fd_my_percentiles)):.1f}th percentile versus the opponent field."
                            )
                    if not _fd_field_salary.empty:
                        st.caption(
                            f"Opponent salary usage: {100.0 * float((_fd_field_salary >= 59000).mean()):.1f}% use at least $59,000; "
                            f"{100.0 * float((_fd_field_salary >= 57000).mean()):.1f}% use at least $57,000."
                        )

                    with st.expander(f"Opponent Lineup Info — {len(_fd_persist_field):,} simulated entries", expanded=False):
                        _fd_opponent_show = _fd_persist_field.copy()
                        _fd_opponent_show["ProjectedPoints"] = pd.to_numeric(_fd_opponent_show.get("ProjectedPoints"), errors="coerce")
                        _fd_opponent_show["Salary"] = pd.to_numeric(_fd_opponent_show.get("Salary"), errors="coerce")
                        _fd_opponent_show = _fd_opponent_show.sort_values("ProjectedPoints", ascending=False, na_position="last")
                        st.caption("Showing the 100 highest-projected simulated opponent lineups. Download contains the full opponent field, including duplicates.")
                        st.dataframe(injury_frame(st, _fd_opponent_show.head(100)), use_container_width=True, hide_index=True)
                        st.download_button(
                            "Download Full Opponent Field CSV",
                            data=_fd_opponent_show.to_csv(index=False).encode("utf-8"),
                            file_name="fanduel_" + lineup_mode.replace(" ", "_").lower() + "_opponent_field.csv",
                            mime="text/csv",
                            key="fd_download_opponent_field_" + lineup_mode.replace(" ", "_").lower(),
                            on_click="ignore",
                        )
                else:
                    st.caption("FanDuel field sanity and opponent lineup info will appear here after Contest SIM builds the opponent field.")

            _fd_rank_options = [label for label, column in PORTFOLIO_METRICS.items() if column in fd_rank_source.columns]
            fd_rank_label = st.selectbox(
                "Rank lineups by", _fd_rank_options, index=_fd_rank_options.index("Top 1%") if "Top 1%" in _fd_rank_options else 0,
                key="fd_rank_metric_top1_default_v2_" + lineup_mode.replace(" ", "_").lower()
            )
            fd_rank_column = PORTFOLIO_METRICS[fd_rank_label]
            fd_rank_source = fd_rank_source.sort_values(fd_rank_column, ascending=False, kind="stable").reset_index(drop=True)
            fd_rank_count = st.number_input(
                "Number of lineups to show", min_value=1, max_value=max(1, len(fd_rank_source)),
                value=min(20, max(1, len(fd_rank_source))), step=1,
                key="fd_rank_count_" + lineup_mode.replace(" ", "_").lower()
            )
            st.caption("Run SIM/contest comparison first for field-based estimates. Without a completed comparison, ranking uses the available lineup results as a temporary estimate.")
            # Keep all built lineups for export. The display limit only controls
            # how many rows are shown on screen, not how many get downloaded.
            fd_all_ranked = fd_rank_source.copy()
            _fd_diverse_portfolio = None
            if lineup_mode in ("Full Roster", "Single Game"):
                from simmah_portfolio_selection import select_portfolio, put_portfolio_first
                _fd_owned_count = full_roster_contest_parameters(st.session_state.get("selected_fd_contest") or {}, 1)["owned"]
                try:
                    _fd_diverse_portfolio = select_portfolio(fd_all_ranked, fd_slots, _fd_owned_count, fd_rank_column,
                        controls=fd_player_display.set_index("Name").to_dict("index"), diversity=portfolio_diversity)
                except ValueError as exc:
                    st.error(str(exc))
                    workspace_stop(st, _loaded_slate_tabs)
                if _fd_diverse_portfolio.attrs.get("effective_auto_cap_pct", 100) > (100 - .4 * portfolio_diversity):
                    st.warning(f"The candidate pool cannot fill all assigned entries at the preferred exposure cap. Automatic cap increased to {_fd_diverse_portfolio.attrs['effective_auto_cap_pct']}%; your manual exposure limits remain enforced.")
                fd_all_ranked = put_portfolio_first(fd_all_ranked, _fd_diverse_portfolio, fd_slots)
                st.caption(f"Lineup exposure diversity: {portfolio_diversity}%. Preferred player cap: {100 - .4 * portfolio_diversity:.0f}%. Locks and manual limits remain enforced. Candidate alternatives remain available below.")
            with _tab_lineups:
                _fd_diverse_portfolio = render_editor(st, _fd_diverse_portfolio, fd_players, fd_slots,
                    "FanDuel", lineup_mode, st.session_state.get("selected_fd_contest", {}),
                    validator=(lambda row: full_roster_stack_matches(row, fd_players, fd_stack_rules, secondary_stacks=fd_secondary_stack_rules)) if lineup_mode == "Full Roster" else single_stack_validator(st, "FanDuel", lineup_mode, full_roster_stack_lookup(fd_players)))
            fd_results = fd_all_ranked.head(int(fd_rank_count)).copy()

            fd_export_portfolio = fd_all_ranked
            if lineup_mode == "Full Roster":
                _fd_selected_contest = st.session_state.get("selected_fd_contest") or {}
                _fd_spec = full_roster_contest_parameters(_fd_selected_contest, 1)
                fd_export_portfolio = _fd_diverse_portfolio.copy()
                _fd_joint_field = st.session_state.get("fd_contest_field_full_roster")
                _fd_joint_outcomes = st.session_state.get("fd_simulation_df_full_roster")
                _fd_context = st.session_state.get("fd_full_roster_evaluation_context")
                if isinstance(_fd_joint_field, pd.DataFrame) and not _fd_joint_field.empty and isinstance(_fd_joint_outcomes, pd.DataFrame) and _fd_context == _fd_selected_contest:
                    _fd_spec = full_roster_contest_parameters(_fd_selected_contest, len(_fd_joint_field))
                    with st.spinner("Evaluating assigned FanDuel entries together..."):
                        fd_export_portfolio = evaluate_full_roster_portfolio_cached(_fd_joint_outcomes, fd_export_portfolio,
                            _fd_joint_field, fd_slots, _fd_spec["field_size"], _fd_spec["tiers"], _fd_spec["fee"])
                    if not _fd_spec["payouts_known"]:
                        fd_export_portfolio = fd_export_portfolio.drop(columns=["CashRate", "Expected Prize ($)", "Expected Net ($)", "Expected ROI (%)", "Entry Fee ($)"], errors="ignore")
                        fd_export_portfolio["ContestScore"] = fd_export_portfolio["Top1"]
                else:
                    st.warning("Run CONTEST SIM for the selected contest before exporting evaluated entries.")
                    fd_export_portfolio = fd_export_portfolio.drop(columns=["CashRate", "Expected Prize ($)", "Expected Net ($)", "Expected ROI (%)", "Entry Fee ($)"], errors="ignore")
                st.session_state["fd_full_roster_assigned_portfolio"] = fd_export_portfolio.copy()
                st.write("### Assigned contest portfolio")
                st.caption(f"These {_fd_spec['owned']} entries are the source for both downloads. Additional displayed candidates are alternatives.")
                st.dataframe(injury_frame(st, fd_export_portfolio), use_container_width=True, hide_index=True)
                st.caption("Candidate alternatives — the assigned portfolio above is used for your entry replacement.")

            if lineup_mode == "Single Game":
                _fd_single_owned = int((st.session_state.get("selected_fd_contest") or {}).get("your_entries") or len(fd_results))
                fd_export_portfolio = _fd_diverse_portfolio.copy()
                _single_field = st.session_state.get("fd_contest_field_single_game")
                _single_outcomes = st.session_state.get("fd_simulation_df_single_game")
                if st.session_state.get("fd_single_game_evaluation_engine") == "shared-contest-mvp-v1" and st.session_state.get("fd_single_game_evaluation_context") == dict(st.session_state.get("selected_fd_contest") or {}) and isinstance(_single_field, pd.DataFrame) and isinstance(_single_outcomes, pd.DataFrame):
                    _single_spec = full_roster_contest_parameters(st.session_state.get("selected_fd_contest"), len(_single_field))
                    fd_export_portfolio = evaluate_full_roster_portfolio_cached(_single_outcomes, fd_export_portfolio,
                        _single_field, fd_slots, _single_spec["field_size"], _single_spec["tiers"], _single_spec["fee"],
                        multipliers=(1.5, 1, 1, 1, 1, 1))
                    if not _single_spec["payouts_known"]:
                        fd_export_portfolio = fd_export_portfolio.drop(columns=["CashRate", "Expected Prize ($)", "Expected Net ($)", "Expected ROI (%)", "Entry Fee ($)"], errors="ignore")
                st.write("### Assigned contest portfolio")
                st.caption("These lineups are used for both the portfolio report and entry replacement.")
                st.dataframe(injury_frame(st, fd_export_portfolio), use_container_width=True, hide_index=True)

            st.session_state["fd_assigned_display_" + lineup_mode.replace(" ", "_").lower()] = fd_export_portfolio.copy()
            st.write("### Candidate Lineups")
            # Use the same player-by-player points layout as the DraftKings Portfolio.
            fd_display = fd_results.copy()
            fd_player_means = {
                str(name): float(values.get("Mean", 0.0))
                for name, values in player_sim.items()
            }
            if isinstance(fd_all_ranked, pd.DataFrame) and not fd_all_ranked.empty:
                _fd_all_candidates_export = fd_all_ranked.copy()
                st.download_button(
                    "DOWNLOAD ALL CANDIDATE LINEUPS",
                    data=_fd_all_candidates_export.to_csv(index=False).encode("utf-8"),
                    file_name="fanduel_" + lineup_mode.replace(" ", "_").lower() + "_all_candidate_lineups.csv",
                    mime="text/csv",
                    key="download_fd_all_candidate_lineups_" + lineup_mode.replace(" ", "_").lower(),
                    on_click="ignore",
                    use_container_width=True,
                )
            fd_display_columns = []
            for slot in fd_slots:
                if slot not in fd_display.columns:
                    continue
                multiplier = 1.5 if slot in {"MVP"} else 1.0
                points_col = slot + " Sim Pts"
                fd_display[points_col] = fd_display[slot].map(
                    lambda player: round(fd_player_means.get(str(player), 0.0) * multiplier, 2)
                )
                fd_display_columns.extend([slot, points_col])
            if "ProjectedPoints" in fd_display.columns:
                fd_display_columns.append("ProjectedPoints")
            if "Score" in fd_display.columns:
                fd_display_columns.append("Score")
            if "Salary" in fd_display.columns:
                fd_display_columns.append("Salary")
            # FanDuel contest comparison already calculates these metrics. Keep them
            # visible in the post-SIM portfolio table so the completed contest run is
            # not reduced back to only projection/score/salary after workspace_rerun(st, _loaded_slate_tabs).
            for metric_col in [
                "ContestScore", "WinRate", "Top1", "Top5", "Top10", "CashRate",
                "AvgPercentile", "Entry Fee ($)", "Expected Prize ($)",
                "Expected Net ($)", "Expected ROI (%)", "Estimated Full Field Rank",
                "Exact Matches in Final Field", "Estimated Field Copies",
            ]:
                if metric_col in fd_display.columns:
                    fd_display_columns.append(metric_col)
            fd_display_columns = list(dict.fromkeys(
                col for col in fd_display_columns if col in fd_display.columns
            ))
            st.dataframe(
                injury_frame(st, fd_display[fd_display_columns] if fd_display_columns else fd_display),
                use_container_width=True,
                hide_index=True
            )

            render_portfolio_roi_panel(fd_export_portfolio, st.session_state.get("selected_fd_contest"))
            st.write("### Export to FanDuel")
            st.caption("Use the entry file below to update your reserved FanDuel entries.")
            with st.expander("Analysis report (optional)", expanded=False):
                lineup_export_download(
                    "DOWNLOAD PORTFOLIO REPORT (FOR REVIEW)",
                    fd_export_portfolio.to_csv(index=False).encode("utf-8"),
                    "FanDuel_Assigned_Portfolio_Report.csv", "text/csv",
                    key="fd_portfolio_report_top_" + lineup_mode.replace(" ", "_").lower(),
                    on_click="ignore", use_container_width=True,
                )
            render_entry_export_header("FanDuel")
            if "FD_ID" in fd_players.columns:
                if fd_entry_file is None or not st.session_state.get("selected_fd_contest"):
                    st.warning("Upload the original FanDuel entries template and select your contest to enable the entry download.")
                else:
                    try:
                        from simmah_exports import build_fanduel_entry_export
                        fd_ids = dict(zip(fd_players["Name"], fd_players["FD_ID"].astype(str)))
                        fd_entry_bytes, fd_entry_count = build_fanduel_entry_export(
                            fd_entry_file.getvalue(), fd_export_portfolio, fd_ids,
                            st.session_state["selected_fd_contest"], lineup_mode)
                        import csv as _fd_export_csv
                        import io as _fd_export_io
                        _fd_upload_rows = list(_fd_export_csv.reader(_fd_export_io.StringIO(fd_entry_bytes.decode("utf-8-sig"))))
                        _fd_upload_header = [c.strip().casefold() for c in _fd_upload_rows[0]]
                        if not set(_fd_upload_header).intersection({"entry_id", "entry id", "entryid"}) or not set(_fd_upload_header).intersection({"contest_id", "contest id", "contestid"}):
                            raise ValueError("Export blocked: replacement CSV is missing reserved entry identifiers.")
                        _fd_export_name = "FanDuel_" + lineup_mode.replace(" ", "_") + "_" + str(st.session_state["selected_fd_contest"]["id"]) + "_UPLOAD.csv"
                        st.success(f"Ready to replace {fd_entry_count} reserved entries. Entry IDs and original template details are preserved.")
                        st.caption("FanDuel upload file: " + _fd_export_name + ". This file contains entry_id, contest_id, and roster player IDs.")
                        with st.expander("Preview FanDuel upload IDs", expanded=False):
                            _fd_preview_text = _fd_export_io.StringIO()
                            _fd_export_csv.writer(_fd_preview_text).writerows([row[:10 if lineup_mode == "Single Game" else 13] for row in _fd_upload_rows[:3]])
                            st.code(_fd_preview_text.getvalue(), language="csv")
                        lineup_export_download(
                            f"EXPORT TO FANDUEL — {fd_entry_count} ENTRIES",
                            fd_entry_bytes,
                            file_name=_fd_export_name,
                            mime="text/csv", use_container_width=True, type="primary",
                            key="fd_entry_upload_v2_" + lineup_mode.replace(" ", "_").lower() + "_" + str(st.session_state["selected_fd_contest"]["id"]), on_click="ignore")
                        st.caption("Export saves a timestamped player snapshot and the exact entry CSV for later comparison.")
                    except Exception as exc:
                        st.error(f"Could not create FanDuel replacement CSV: {exc}")
            else:
                st.info("This CSV has no player ID column, so lineup export is unavailable.")


        # Populate the earlier download location after SIM/BUILD has updated this
        # run's session state. The download's bytes must not capture pre-SIM values.
        from simmah_player_display import scoring_input_report
        _fd_scoring_report = scoring_input_report(fd_player_display,
            st.session_state.get("fd_simulation_df_" + lineup_mode.replace(" ", "_").lower()))
        _fd_fit_report = st.session_state.get("projection_event_fit_FanDuel")
        if isinstance(_fd_fit_report, pd.DataFrame) and not _fd_fit_report.empty:
            _fd_fit_cols = [c for c in ["Name", "Before Calibration", "Pilot Mean", "Passing Input", "Opportunity Input", "Skill Gain Input", "Calibration Status"] if c in _fd_fit_report]
            _fd_scoring_report = _fd_scoring_report.merge(_fd_fit_report[_fd_fit_cols], on="Name", how="left")
        _fd_scoring_download_slot.download_button("DOWNLOAD PLAYER SCORING INPUTS", _fd_scoring_report.to_csv(index=False).encode("utf-8"),
            "FanDuel_" + lineup_mode.replace(" ", "_") + "_Player_Scoring_Inputs.csv", "text/csv",
            key="fd_player_scoring_inputs_" + lineup_mode.replace(" ", "_").lower(), on_click="ignore")
        workspace_stop(st, _loaded_slate_tabs)

else:

    # ================================
    # PLAYER POOL
    # ================================

    players_df = pd.DataFrame(columns=["Name", "Position", "Team", "Salary", "Projection"])

    # ================================
    # DRAFTKINGS SALARY FILE UPLOAD
    # ================================

    # The universal uploader supplies both salary references and reserved entries.
    dk_slate_file = auto_slate_file
    salary_file = dk_slate_file
    entry_file = dk_slate_file
    if dk_slate_file is None:
        with _tab_roster:
            st.info("Upload your entries/slate CSV in Contests to load this slate's player pool.")
        with _tab_lineups:
            st.info("Your assigned lineups will appear here after you load a slate and run a build.")
        workspace_stop(st, _loaded_slate_tabs)

    with _contest_setup:
        selected_contest_id = None
        selected_contest_name = None
        selected_contest_entry_count = 0
        selected_contest_entry_fee = None

        if entry_file is not None:
            try:
                # DraftKings' My Contests download may include instructions and a salary table
                # after the entries, and some contest names may contain unquoted commas.
                # Parse the entry rows explicitly so those extra sections cannot shift the
                # Contest ID or roster columns.
                import csv
                import io

                entry_file.seek(0)
                raw_entry_text = entry_file.getvalue().decode("utf-8-sig", errors="replace")
                parsed_rows = list(csv.reader(io.StringIO(raw_entry_text)))
                if not parsed_rows:
                    st.error("The uploaded DraftKings contest entry CSV is empty.")
                    workspace_stop(st, _loaded_slate_tabs)

                raw_header = [str(col).strip() for col in parsed_rows[0]]
                header_lookup = {str(col).strip().casefold(): i for i, col in enumerate(raw_header)}
                required_header_names = {"entry id", "contest name", "contest id", "entry fee"}
                if not required_header_names.issubset(header_lookup):
                    st.error(
                        "This CSV does not appear to be a DraftKings My Contests entry file. "
                        "Please upload the original contest entry CSV, not the salary CSV."
                    )
                    workspace_stop(st, _loaded_slate_tabs)

                # Keep the roster headers from the uploaded entry file. DraftKings
                # Classic and Showdown use different roster layouts, and duplicate slot
                # names (RB, WR, FLEX) are normal in these CSVs.
                metadata_headers = ["Entry ID", "Contest Name", "Contest ID", "Entry Fee"]
                roster_headers = [
                    str(col).strip()
                    for col in raw_header[4:]
                    if str(col).strip() and str(col).strip().casefold() != "instructions"
                ]
                if not roster_headers:
                    st.error("Could not find player-slot columns in this DraftKings entry CSV.")
                    workspace_stop(st, _loaded_slate_tabs)

                # Validate the uploaded contest-entry template against the selected format.
                normalized_slots = [str(slot).strip().upper() for slot in roster_headers]
                entry_is_showdown = any(slot == "CPT" for slot in normalized_slots)
                if lineup_mode == "Showdown" and not entry_is_showdown:
                    st.error(
                        "This is not a DraftKings Showdown entry file: its roster columns do not include CPT. "
                        "Select DraftKings Classic or upload the correct Showdown entries file."
                    )
                    workspace_stop(st, _loaded_slate_tabs)
                if lineup_mode == "Classic" and entry_is_showdown:
                    st.error(
                        "This is a DraftKings Showdown entry file (CPT/FLEX), but DraftKings Classic is selected. "
                        "Select DraftKings Showdown or upload the correct Classic entries file."
                    )
                    workspace_stop(st, _loaded_slate_tabs)

                parsed_entries = []
                repaired_count = 0
                ignored_rows = 0
                roster_count = len(roster_headers)

                for fields in parsed_rows[1:]:
                    if not fields or not str(fields[0]).strip().isdigit():
                        ignored_rows += 1
                        continue

                    # Entry ID is column A. Contest ID is the first all-digit field after
                    # it; joining the fields before it repairs unquoted commas in contest names.
                    contest_id_index = next(
                        (i for i in range(2, len(fields)) if str(fields[i]).strip().isdigit()),
                        None
                    )
                    if contest_id_index is None or contest_id_index + 1 + roster_count >= len(fields):
                        ignored_rows += 1
                        continue

                    if contest_id_index != 2:
                        repaired_count += 1

                    entry_id = str(fields[0]).strip()
                    contest_name = ",".join(str(v) for v in fields[1:contest_id_index]).strip()
                    contest_id = str(fields[contest_id_index]).strip()
                    entry_fee = str(fields[contest_id_index + 1]).strip()
                    roster = [
                        str(v).strip()
                        for v in fields[contest_id_index + 2:contest_id_index + 2 + roster_count]
                    ]

                    # Output only the actual roster columns and omit appended instructions/player-pool rows.
                    parsed_entries.append([entry_id, contest_name, contest_id, entry_fee, *roster])

                if not parsed_entries:
                    st.error(
                        "No valid contest entry rows were found. Please upload the original "
                        "DraftKings My Contests CSV."
                    )
                    workspace_stop(st, _loaded_slate_tabs)

                standard_header = metadata_headers + roster_headers
                entry_df = pd.DataFrame(parsed_entries, columns=standard_header)

                if repaired_count:
                    st.info(
                        f"Read {len(parsed_entries)} contest entries and corrected "
                        f"{repaired_count} row(s) with commas in contest names. "
                        "Appended instructions and salary rows were ignored."
                    )
                entry_df.columns = [str(c).strip() for c in entry_df.columns]
                required_entry_columns = {"Contest Name", "Contest ID"}
                if required_entry_columns.issubset(entry_df.columns):
                    entry_df["Contest ID"] = entry_df["Contest ID"].astype(str).str.replace(r"\.0$", "", regex=True)
                    # DraftKings exports can contain blank Entry ID cells when the CSV columns
                    # are shifted or the file is a lineup template. Only deduplicate rows with
                    # a real entry ID; keep rows with missing IDs so the entry count is not
                    # incorrectly reduced to one.
                    if "Entry ID" in entry_df.columns:
                        entry_ids = entry_df["Entry ID"].fillna("").astype(str).str.strip()
                        has_entry_id = entry_ids.ne("") & entry_ids.str.casefold().ne("nan")
                        identified = remove_duplicate_entries(entry_df.loc[has_entry_id].copy(), "Entry ID")
                        unidentified = entry_df.loc[~has_entry_id].copy()
                        entry_df = pd.concat([identified, unidentified], ignore_index=True)
                    else:
                        entry_df = remove_duplicate_entries(entry_df, None)
                    entry_df = entry_df[
                        entry_df["Contest Name"].fillna("").astype(str).apply(is_full_game_contest_name)
                    ].copy()
                    if entry_df.empty:
                        st.warning("No full-game DraftKings contests were found in this entry file.")
                    contest_summary = (
                        entry_df.groupby(["Contest ID", "Contest Name"], dropna=False)
                        .agg(
                            Entries=("Entry ID", "size") if "Entry ID" in entry_df.columns else ("Contest ID", "size"),
                            EntryFee=("Entry Fee", "first") if "Entry Fee" in entry_df.columns else ("Contest ID", "size")
                        )
                        .reset_index()
                    )
                    if contest_summary.empty:
                        st.warning("No usable contest rows were found in this entry CSV. Please upload the original DraftKings My Contests CSV.")
                        selected_row = pd.Series({"Contest ID": "", "Contest Name": "", "Entries": len(entry_df), "EntryFee": None})
                    else:
                        contest_summary["Contest Label"] = contest_summary.apply(
                            lambda row: (
                                f"{row['Contest Name']} | {int(row['Entries'])} entries | "
                                f"ID {row['Contest ID']}"
                            ),
                            axis=1,
                        )
                        selected_label = st.selectbox(
                            "Contest",
                            contest_summary["Contest Label"].tolist(),
                            key=f"dk_one_upload_contest_{lineup_mode.lower().replace(' ', '_')}",
                        )
                        selected_row = contest_summary.loc[
                            contest_summary["Contest Label"].eq(selected_label)
                        ].iloc[0]
                    selected_contest_id = str(selected_row["Contest ID"])
                    selected_contest_name = str(selected_row["Contest Name"]).strip()
                    if selected_contest_name.casefold() in {"", "nan", "none"} or set(selected_contest_name) <= {","}:
                        selected_contest_name = "Contest name not detected — check uploaded CSV format"
                    selected_contest_entry_count = int(selected_row["Entries"])
                    selected_contest_entry_fee = pd.to_numeric(
                        str(selected_row["EntryFee"]).replace("$", "").replace(",", ""),
                        errors="coerce"
                    )
                    st.session_state["selected_dk_contest"] = {
                        "id": selected_contest_id,
                        "name": selected_contest_name,
                        "your_entries": selected_contest_entry_count,
                        "entry_fee": (
                            float(selected_contest_entry_fee)
                            if pd.notna(selected_contest_entry_fee) else None
                        ),
                    }
                    fee_text = (
                        f"${float(selected_contest_entry_fee):.2f}"
                        if pd.notna(selected_contest_entry_fee) else "not listed"
                    )
                    st.success(
                        f"Selected: {selected_contest_name} | Contest ID: {selected_contest_id} | "
                        f"Your entries in this file: {selected_contest_entry_count} | Entry fee: {fee_text}"
                    )
                    st.caption(
                        "This file identifies your contest and your entries. It does not provide the full opponent field or payout table, "
                        "so those details are not assumed by the simulator yet."
                    )
                else:
                    st.error("This CSV does not appear to be a DraftKings contest entry file. It needs Contest Name and Contest ID columns.")
            except Exception as exc:
                st.error(f"Could not read the DraftKings contest entry file: {exc}")

        # DraftKings players and salaries are loaded only from the uploaded salary CSV.
        selected_dk_draft_group_id = None
        auto_draftables_df = None

        dk_slate_key = "showdown" if lineup_mode == "Showdown" else "classic"
        dk_saved_contests = st.session_state.get("selected_dk_contests_by_slate", {})
        previous_selection = dk_saved_contests.get(dk_slate_key, {})
        if selected_contest_name:
            active_dk_selection = {
                "id": str(selected_contest_id or ""),
                "name": str(selected_contest_name),
                "your_entries": int(selected_contest_entry_count or 0),
                "entry_fee": (
                    float(selected_contest_entry_fee)
                    if selected_contest_entry_fee is not None and pd.notna(selected_contest_entry_fee)
                    else None
                ),
                # Keep the user's field-size setting when contest details are refreshed.
                "field_size": previous_selection.get("field_size"),
            }
            st.caption("Using contest details from your uploaded DraftKings entry CSV.")
        else:
            active_dk_selection = {
                "id": str(previous_selection.get("id", "")),
                "name": str(previous_selection.get("name", "")),
                "your_entries": int(previous_selection.get("your_entries", 0) or 0),
                "entry_fee": previous_selection.get("entry_fee"),
                "field_size": None,
            }

        dk_saved_contests[dk_slate_key] = active_dk_selection
        st.session_state["selected_dk_contests_by_slate"] = dk_saved_contests
        st.session_state["selected_dk_contest"] = active_dk_selection

        # Pull the current contest size automatically from DraftKings when available.
        # Keep the manual input only as a fallback if DraftKings does not return usable details.
        previous_field_size = active_dk_selection.get("field_size")
        _rounded_capacity_estimate = 59400 if str(active_dk_selection.get("id", "")) == "196786696" else None
        if _rounded_capacity_estimate:
            previous_field_size = _rounded_capacity_estimate
        auto_current_entries, auto_max_entries = fetch_draftkings_contest_size(
            active_dk_selection.get("id")
        )
        # Pregame contest simulation should use the contest capacity when DraftKings
        # provides it. Using current entries while a contest is still filling makes
        # estimated ranks, cash rates, payouts, and ROI too optimistic.
        # Exact capacity supplied from the contest details, scoped to this contest.
        if str(active_dk_selection.get("id", "")) == "196786594" and not auto_max_entries:
            auto_max_entries = 35671
        if str(active_dk_selection.get("id", "")) == "196867391" and not auto_max_entries:
            auto_max_entries = 3567
        auto_field_size = auto_max_entries or (None if _rounded_capacity_estimate else auto_current_entries)

        try:
            fallback_field_size = int(previous_field_size) if previous_field_size else 45396
        except (TypeError, ValueError):
            fallback_field_size = 45396

        if auto_field_size is not None and int(auto_field_size) >= 2:
            active_field_size = int(auto_field_size)
            if auto_max_entries:
                st.success(f"Contest capacity loaded automatically from DraftKings: {active_field_size:,} entries")
            else:
                st.success(f"Contest field size loaded automatically from DraftKings: {active_field_size:,} entries")
            if auto_current_entries and auto_max_entries and auto_max_entries >= auto_current_entries:
                st.caption(f"Current entries: {auto_current_entries:,} of {auto_max_entries:,} maximum. Pregame ROI uses the maximum field size.")
        else:
            active_field_size = st.number_input(
                "Contest field size (fallback only)",
                min_value=2,
                max_value=200000,
                value=max(2, min(200000, fallback_field_size)),
                step=100,
                key=f"dk_field_capacity_v2_{dk_slate_key}_{active_dk_selection.get('id', 'unknown')}",
                help="Enter the exact maximum contest capacity, not the current registration count. For contest 196786696, 59,400 is an estimate from the rounded 59.4K display until the exact capacity is confirmed."
            )
            st.caption("SIMMAH uses this manual capacity when the DraftKings contest lookup is unavailable.")
            if _rounded_capacity_estimate and int(active_field_size) == _rounded_capacity_estimate:
                st.warning("59,400 is estimated from the rounded 59.4K lobby capacity. Enter the exact maximum capacity when available; ROI remains an estimate.")

        active_dk_selection["field_size"] = int(active_field_size)
        from simmah_saved_contests import render_panel as render_saved_contest_panel
        active_dk_selection = render_saved_contest_panel(st, active_dk_selection, selected_format)
        active_field_size = int(active_dk_selection.get("field_size") or active_field_size)
        dk_saved_contests[dk_slate_key] = active_dk_selection
        st.session_state["selected_dk_contests_by_slate"] = dk_saved_contests
        st.session_state["selected_dk_contest"] = active_dk_selection

        dk_opponent_target = get_contest_opponent_target("dk")
        st.caption(
            f"Simulated opponent sample: up to {dk_opponent_target:,}; "
            f"estimated full contest: {int(active_field_size):,} total entries."
        )

    with _tab_roster:
        st.write("### Projection Sources")

        # Optional uploaded projection files; automatic public-source refresh is handled
        # by apply_external_projection_sources when these are not supplied.
        with st.expander("Upload projections / restore saved pregame inputs", expanded=False):
            st.caption("Uploads take priority over automatic projections. To restore saved point projections, upload the pregame player-input CSV below.")
            _dk_saved_projection_file = workspace_file_uploader(st,
                "Saved pregame player inputs CSV", type=["csv"],
                key="dk_saved_projection_upload_" + lineup_mode.replace(" ", "_").lower())
            _dk_projection_cols = st.columns(2)
            with _dk_projection_cols[0]:
                _dk_manual_dff = workspace_file_uploader(st,"DFF projections CSV (optional)", type=["csv"],
                    key="dk_dff_projection_upload_" + lineup_mode.replace(" ", "_").lower())
            with _dk_projection_cols[1]:
                _dk_manual_draftedge = workspace_file_uploader(st,"DraftEdge projections CSV (optional)", type=["csv"],
                    key="dk_draftedge_projection_upload_" + lineup_mode.replace(" ", "_").lower())
            if _dk_saved_projection_file is not None:
                st.caption("Saved point projections supplied to both sources to preserve the saved averages. Injury and weather checks remain current.")
        dff_projection_file = _dk_saved_projection_file if _dk_saved_projection_file is not None else _dk_manual_dff
        draftedge_projection_file = _dk_saved_projection_file if _dk_saved_projection_file is not None else _dk_manual_draftedge
        show_projection_refresh_status(
            [("DFF", dff_projection_file), ("DraftEdge", draftedge_projection_file)],
            "dk_" + lineup_mode.replace(" ", "_").lower()
        )

        if salary_file is not None:
            try:
                # Block a clearly mislabeled DraftKings format before it can replace the active player pool.
                uploaded_filename = str(getattr(salary_file, "name", "")).casefold()
                filename_says_showdown = any(term in uploaded_filename for term in ("showdown", "single game", "single_game"))
                filename_says_classic = any(term in uploaded_filename for term in ("classic", "full roster", "full_roster"))
                if lineup_mode == "Classic" and filename_says_showdown:
                    raise ValueError("This filename indicates a DraftKings Showdown CSV, but Classic is selected. Select Showdown or upload the correct Classic CSV. The current player pool was not replaced.")
                if lineup_mode == "Showdown" and filename_says_classic:
                    raise ValueError("This filename indicates a DraftKings Classic CSV, but Showdown is selected. Select Classic or upload the correct Showdown CSV. The current player pool was not replaced.")

                # DraftKings lineup templates have instructions before the player table.
                # Detect that format and skip those rows; ordinary salary CSVs load normally.
                salary_file.seek(0)
                first_lines = salary_file.getvalue().decode("utf-8-sig", errors="replace").splitlines()
                header_line = next(
                    (i for i, line in enumerate(first_lines)
                     if "Roster Position" in line and "AvgPointsPerGame" in line),
                    None
                )
                is_lineup_template = header_line is not None
                is_showdown_template = False

                salary_file.seek(0)
                if is_lineup_template:
                    uploaded_df = pd.read_csv(salary_file, skiprows=header_line)
                    uploaded_df.columns = [str(c).strip() for c in uploaded_df.columns]
                    roster_col = "Roster Position" if "Roster Position" in uploaded_df.columns else None
                    # Showdown templates repeat each player as CPT and FLEX. Keep FLEX
                    # only for that format; Classic templates must keep all player rows.
                    if roster_col:
                        roster_values = set(
                            uploaded_df[roster_col].astype(str).str.upper().str.strip()
                        )
                        is_showdown_template = "CPT" in roster_values
                        if is_showdown_template and lineup_mode != "Showdown":
                            raise ValueError("This CSV contains DraftKings Showdown CPT/FLEX slots, but Classic is selected. Select Showdown or upload a Classic salary CSV. The current player pool was not replaced.")
                        if not is_showdown_template and lineup_mode == "Showdown":
                            raise ValueError("This appears to be a DraftKings Classic lineup template, but Showdown is selected. Select Classic or upload a Showdown salary CSV. The current player pool was not replaced.")
                        # Save separate CPT/FLEX IDs before keeping one FLEX row per player.
                        if is_showdown_template:
                            template_cols = {str(c).strip().lower(): c for c in uploaded_df.columns}
                            template_name_col = next(
                                (template_cols[c] for c in ["name", "name + id", "player", "player name"] if c in template_cols),
                                None
                            )
                            template_id_col = next(
                                (template_cols[c] for c in ["id", "player id", "dk id"] if c in template_cols),
                                None
                            )
                            dk_id_map = {}
                            if template_name_col is not None and template_id_col is not None:
                                for _, template_row in uploaded_df.iterrows():
                                    template_name = str(template_row[template_name_col]).strip()
                                    template_name = re.sub(r"\s*\\(\\d+\\)\s*$", "", template_name)
                                    template_slot = str(template_row[roster_col]).upper().strip()
                                    template_id = str(template_row[template_id_col]).strip()
                                    if template_name and template_name.lower() != "nan" and template_id and template_id.lower() != "nan":
                                        dk_id_map.setdefault(template_name, {})[template_slot] = template_id
                            st.session_state["dk_player_ids"] = dk_id_map
                            uploaded_df = uploaded_df[
                                uploaded_df[roster_col].astype(str).str.upper().str.strip().eq("FLEX")
                            ].copy()
                else:
                    uploaded_df = pd.read_csv(salary_file)
                    uploaded_df.columns = [str(c).strip() for c in uploaded_df.columns]

                def find_column(frame, choices):
                    lookup = {str(c).strip().lower(): c for c in frame.columns}
                    for choice in choices:
                        if choice.lower() in lookup:
                            return lookup[choice.lower()]
                    return None

                name_col = find_column(uploaded_df, ["Name", "Name + ID", "Player", "Player Name"])
                salary_col = find_column(uploaded_df, ["Salary"])
                team_col = find_column(uploaded_df, ["TeamAbbrev", "Team", "Team Abbrev", "Team Abbreviation"])
                position_col = find_column(uploaded_df, ["Position", "Roster Position", "RosterPosition"])
                # Do not use DraftKings salary-file fantasy averages as projections.
                projection_col = None
                id_col = find_column(uploaded_df, ["ID", "Player ID", "DK ID"])

                missing = []
                if name_col is None:
                    missing.append("player name (Name or Name + ID)")
                if salary_col is None:
                    missing.append("Salary")
                if team_col is None:
                    missing.append("team (TeamAbbrev or Team)")

                if missing:
                    st.error("Could not load the salary file. Missing columns: " + ", ".join(missing) + ". The sample player pool is still being used.")
                else:
                    loaded_players = pd.DataFrame()
                    loaded_players["Name"] = uploaded_df[name_col].astype(str).str.strip()
                    loaded_players["Name"] = loaded_players["Name"].str.replace(r"\s*\(\d+\)\s*$", "", regex=True)
                    loaded_players["Salary"] = pd.to_numeric(
                        uploaded_df[salary_col].astype(str).str.replace(r"[$,]", "", regex=True),
                        errors="coerce"
                    )
                    loaded_players["Team"] = uploaded_df[team_col].astype(str).str.strip().str.upper()
                    for _game_col in uploaded_df.columns:
                        if str(_game_col).lower().replace(" ", "") in {"gameinfo", "game", "starttime", "kickoff"}:
                            loaded_players[_game_col] = uploaded_df[_game_col]

                    show_detected_slate_games(uploaded_df)
                    loaded_players["Position"] = (
                        uploaded_df[position_col].astype(str).str.strip()
                        if position_col is not None else "FLEX"
                    )
                    loaded_players["Projection"] = (
                        pd.to_numeric(uploaded_df[projection_col], errors="coerce")
                        if projection_col is not None else np.nan
                    )
                    if id_col is not None:
                        loaded_players["DK_ID"] = uploaded_df[id_col].astype(str).str.strip()
                    loaded_players = preserve_uploaded_ownership(loaded_players, uploaded_df)
                    # Keep missing projections blank until the DFF refresh below has a chance to fill them.
                    loaded_players["Projection"] = pd.to_numeric(
                        loaded_players["Projection"], errors="coerce"
                    )
                    loaded_players = loaded_players.dropna(subset=["Name", "Salary"])
                    loaded_players = loaded_players[
                        (loaded_players["Name"] != "") &
                        (loaded_players["Name"].str.lower() != "nan") &
                        (loaded_players["Salary"] > 0)
                    ].drop_duplicates(subset=["Name"], keep="first")

                    if loaded_players.empty:
                        st.error("No usable players were found in that file. The sample player pool is still being used.")
                    else:
                        # A Showdown salary file must contain players from exactly one matchup
                        # (two NFL teams); a full-slate salary file must not be accepted.
                        teams_in_file = sorted(
                            set(loaded_players["Team"].astype(str).str.strip().str.upper())
                            - {"", "NAN", "NONE"}
                        )
                        if lineup_mode == "Showdown" and len(teams_in_file) != 2:
                            raise ValueError(
                                f"Showdown requires a salary file for one game (exactly 2 teams). "
                                f"This file contains {len(teams_in_file)} teams: {', '.join(teams_in_file[:12])}. "
                                "Upload the DK Salaries CSV for the specific game."
                            )
                        if lineup_mode == "Classic" and len(teams_in_file) <= 2:
                            raise ValueError(
                                "This salary file contains only one game's teams and looks like a Showdown slate. "
                                "Select DraftKings Showdown or upload the full-slate Classic salary file."
                            )
                        players_df = loaded_players.reset_index(drop=True)
                    # Ignore any projection column in the uploaded salary CSV.
                    players_df["Projection"] = np.nan
                    players_df["ProjectionSource"] = "Internal Simulation"

            except Exception as exc:
                st.error(f"Could not read that CSV: {exc}. Upload a valid entries/slate CSV to continue.")
                workspace_stop(st, _loaded_slate_tabs)



        players_df = apply_injury_statuses(players_df, "injury_status_dk_" + lineup_mode.replace(" ", "_").lower())

        # External projections only: do not calculate or use internal fallback projections.
        players_df["Projection"] = np.nan
        players_df = apply_external_projection_sources(
            players_df,
            dff_projection_file,
            draftedge_projection_file,
            platform_name=("DraftKings Showdown" if lineup_mode == "Showdown" else "DraftKings Classic"),
        )
        dk_valid_projection_count = int(pd.to_numeric(players_df.get("Projection"), errors="coerce").gt(0).sum())
        if dk_valid_projection_count == 0 and not players_df.empty:
            st.warning(
                "Players loaded successfully, but external projections are not available for this slate yet. "
                "Click REFRESH PROJECTIONS + INJURY NEWS later after projections are posted."
            )
        elif dk_valid_projection_count < len(players_df):
            st.info(
                f"Players loaded successfully. Projections are available for {dk_valid_projection_count} of {len(players_df)} players; "
                "players without a posted external projection will stay out of builds until a refresh finds one."
            )

        players_df = apply_game_weather_context(players_df, uploaded_df if "uploaded_df" in locals() else players_df)

        # Keep the full DraftKings salary-file pool visible even when some players do not yet have projections.
        all_dk_players_df = players_df.copy()

        def internal_slate_key(frame):
            """Stable identity for an uploaded slate, independent of external projections."""
            return tuple(
                frame[["Name", "Team", "Position", "Salary"]]
                .astype(str)
                .itertuples(index=False, name=None)
            )

        internal_key = internal_slate_key(all_dk_players_df)
        st.caption("Automatic projection values average all available valid DFF, DraftEdge and RotoWire projections; uploaded CSVs keep priority and a single available source is used directly. All salary-file players remain visible; players without a positive external projection stay out of SIM/BUILD until a refresh finds one.")
        if st.session_state.get("nfl_historical_stats_status"):
            st.caption(st.session_state["nfl_historical_stats_status"])
            if st.session_state.get("nfl_historical_players_matched") is not None:
                st.caption("Historical player matches in current pool: " + str(st.session_state["nfl_historical_players_matched"]))
        if st.session_state.get("nfl_pbp_history_status"):
            st.caption("Play-by-play history: " + st.session_state["nfl_pbp_history_status"])


        opponent_source = uploaded_df if "uploaded_df" in locals() else None
        opponent_map = build_opponent_map(opponent_source, all_dk_players_df["Team"])
        all_dk_players_df["Opponent"] = all_dk_players_df["Team"].map(opponent_map).fillna("—")
        all_dk_players_df["CaptainSalary"] = (all_dk_players_df["Salary"] * 1.5).astype(int)

        # Build/simulate only players with a positive external projection.
        players_df = exclude_zero_projection_players(all_dk_players_df, "DraftKings " + lineup_mode)
        players_df = resolve_quarterback_roles_for_build(players_df, "DraftKings " + lineup_mode)
        players_df["Opponent"] = players_df["Team"].map(opponent_map).fillna("—")
        players_df["CaptainSalary"] = (players_df["Salary"] * 1.5).astype(int)

        # Save results by player pool instead of deleting them when the slate changes.
        # This lets a user return to a previously loaded slate and recover its last build.
        # Stable slate identity: generated projections must not make the slate look new.
        slate_signature = internal_key
        BUILD_STATE_KEYS = [
            "simulation_df", "simulations_ready", "contest_field_df",
            "contest_field_count", "contest_field_ready", "candidates_df",
            "candidates_ready", "contest_results_df", "portfolio_df",
            "portfolio_count_used", "portfolio_metric_used",
            "final_lineups", "dk_player_ids",
            "classic_lineups", "classic_pool_signature"
        ]
        if "saved_builds_by_slate" not in st.session_state:
            st.session_state["saved_builds_by_slate"] = {}

        previous_signature = st.session_state.get("active_slate_signature")
        if previous_signature is not None and previous_signature != slate_signature:
            st.session_state["saved_builds_by_slate"][previous_signature] = {
                key: st.session_state[key]
                for key in BUILD_STATE_KEYS
                if key in st.session_state
            }
            for key in BUILD_STATE_KEYS:
                st.session_state.pop(key, None)

        if previous_signature != slate_signature:
            previous_build = st.session_state["saved_builds_by_slate"].get(slate_signature, {})
            for key, value in previous_build.items():
                st.session_state[key] = value
            st.session_state["active_slate_signature"] = slate_signature

        # Never display a saved DraftKings Classic build if it contains a player who is
        # no longer in the current eligible pool (including players newly marked Out).
        if platform == "DraftKings" and lineup_mode == "Classic":
            saved_classic = st.session_state.get("classic_lineups")
            if saved_classic is not None and not saved_classic.empty:
                classic_slot_columns = [
                    column for column in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
                    if column in saved_classic.columns
                ]
                current_names = set(players_df["Name"].astype(str))
                saved_names = set(
                    saved_classic[classic_slot_columns].astype(str).to_numpy().ravel()
                ) if classic_slot_columns else set()
                if not saved_names.issubset(current_names):
                    st.session_state.pop("classic_lineups", None)
                    st.session_state.pop("classic_pool_signature", None)
                    st.info("The saved Classic lineups were cleared because they included players no longer in the current player pool. Build fresh lineups.")

        # ================================
        # SIMULATION
        # ================================

        def run_game_simulations(players_df, platform="DraftKings", workflow_status=None):
            # Final safety check: Out players must never enter simulations, even if
            # this function is called from a different slate builder or stale UI state.
            eligible_players = players_df.copy()
            if "Injury Status" in eligible_players.columns:
                eligible_players = eligible_players[
                    eligible_players["Injury Status"].astype(str).str.strip().str.casefold() != "out"
                ].copy()
            if eligible_players.empty:
                st.error("No eligible players remain. Change at least one player from Out to Active or Questionable.")
                workspace_stop(st, _loaded_slate_tabs)
            # Simulate stat lines first, then calculate fantasy points with site scoring.
            rng = np.random.default_rng()
            if workflow_status is not None:
                workflow_status.info(f"Step 1 of 4: Running {SIMULATION_COUNT:,} independent shared NFL outcomes...")
            outcomes = simulate_fd_play_by_play(
                eligible_players, rng, n=SIMULATION_COUNT,
                correlation_strength=(1.0 if lineup_mode == "Classic" else
                                      float(st.session_state.get("active_game_correlation_strength", 0.0))),
                platform="DraftKings",
            )
            if lineup_mode == "Classic":
                st.session_state["dk_classic_sim_engine"] = "Shared NFL PBP v2"
            # Show Step 2 as soon as the player outcomes finish, before the historical-data check.
            if workflow_status is not None:
                workflow_status.info("Step 2 of 4: Preparing rankings and building your candidate lineups...")
            # Do not load historical datasets in the critical SIM workflow. This extra
            # diagnostic can be slow and is unrelated to building the current slate.
            # Keeping it out of the button path lets Step 2 and lineup building proceed
            # immediately after the player outcomes finish.
            return outcomes

        # ================================
        # PLAYER DISPLAY
        # ================================

        st.divider()
        st.write("### Player Pool — Stats, Simulation, Exposure & Controls")

        player_display = all_dk_players_df.copy()

        # Show exposure from the current slate's built lineups.
        # Classic uses overall exposure only; Showdown uses Captain/Flex exposure.
        if platform == "DraftKings" and lineup_mode == "Classic":
            classic_for_exposure = st.session_state.get("classic_lineups")
            classic_slots = [
                c for c in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
                if isinstance(classic_for_exposure, pd.DataFrame) and c in classic_for_exposure.columns
            ]
            if isinstance(classic_for_exposure, pd.DataFrame) and not classic_for_exposure.empty and classic_slots:
                exposure_lineups = len(classic_for_exposure)
                appearances = (
                    classic_for_exposure[classic_slots]
                    .astype(str)
                    .apply(lambda row: pd.unique(row.str.strip()).tolist(), axis=1)
                    .explode()
                    .value_counts()
                )
                player_names = player_display["Name"].astype(str).str.strip()
                player_display["Exposure %"] = player_names.map(
                    lambda name: round(100 * appearances.get(name, 0) / exposure_lineups, 1)
                )
            else:
                player_display["Exposure %"] = np.nan
        else:
            portfolio_for_exposure = st.session_state.get("portfolio_df")
            if (
                isinstance(portfolio_for_exposure, pd.DataFrame)
                and not portfolio_for_exposure.empty
                and "Captain" in portfolio_for_exposure.columns
            ):
                exposure_lineups = len(portfolio_for_exposure)
                captain_counts = portfolio_for_exposure["Captain"].astype(str).str.strip().value_counts()
                flex_columns = [c for c in ["Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
                                if c in portfolio_for_exposure.columns]
                if flex_columns and exposure_lineups:
                    flex_counts = (
                        portfolio_for_exposure[flex_columns]
                        .astype(str)
                        .apply(lambda row: pd.unique(row.str.strip()).tolist(), axis=1)
                        .explode()
                        .value_counts()
                    )
                else:
                    flex_counts = pd.Series(dtype=int)
                player_names = player_display["Name"].astype(str).str.strip()
                player_display["Captain Exp %"] = player_names.map(
                    lambda name: round(100 * captain_counts.get(name, 0) / exposure_lineups, 1)
                )
                player_display["Flex Exp %"] = player_names.map(
                    lambda name: round(100 * flex_counts.get(name, 0) / exposure_lineups, 1)
                )
            else:
                player_display["Captain Exp %"] = np.nan
                player_display["Flex Exp %"] = np.nan

        # Keep three overall ownership views side by side. Showdown also keeps the
        # existing Captain Exp % and Flex Exp % columns for the user's portfolio.
        # Projected Own % = pre-contest ownership estimate.
        # Mine Own % = exposure in the user's current selected portfolio/build.
        # Field Own % = ownership observed in the simulated opponent field.
        ownership_lookup = {str(c).strip().casefold(): c for c in player_display.columns}
        projected_own_col = next((ownership_lookup[k] for k in (
            "projected ownership", "projected own", "ownership %", "ownership", "own%", "own"
        ) if k in ownership_lookup), None)
        if projected_own_col is not None:
            player_display["Projected Own %"] = pd.to_numeric(
                player_display[projected_own_col].astype(str).str.replace("%", "", regex=False),
                errors="coerce",
            ).clip(lower=0.0, upper=100.0).round(1)
        else:
            # Match the ownership proxy already used by lineup ranking when no
            # external ownership column is available.
            projection_values = pd.to_numeric(player_display.get("Projection"), errors="coerce")
            if projection_values is not None and projection_values.notna().any():
                projection_ranks = projection_values.rank(pct=True, method="average")
                player_display["Projected Own %"] = (5.0 + 30.0 * projection_ranks).clip(0.0, 100.0).round(1)
                player_display.loc[projection_values.isna() | projection_values.le(0), "Projected Own %"] = np.nan
            else:
                player_display["Projected Own %"] = np.nan

        if platform == "DraftKings" and lineup_mode == "Showdown":
            own_captain = pd.to_numeric(player_display.get("Captain Exp %"), errors="coerce")
            own_flex = pd.to_numeric(player_display.get("Flex Exp %"), errors="coerce")
            if own_captain is not None and own_flex is not None:
                player_display["Mine Own %"] = (own_captain.fillna(0.0) + own_flex.fillna(0.0)).clip(upper=100.0).round(1)
                no_own_data = own_captain.isna() & own_flex.isna()
                player_display.loc[no_own_data, "Mine Own %"] = np.nan
            else:
                player_display["Mine Own %"] = np.nan
        elif "Exposure %" in player_display.columns:
            player_display["Mine Own %"] = pd.to_numeric(
                player_display["Exposure %"], errors="coerce"
            ).round(1)
        else:
            player_display["Mine Own %"] = np.nan

        # Add simulated opponent-field ownership beside the user's own exposure columns.
        # Full-roster formats use overall ownership. Single-game formats show special-slot
        # and FLEX ownership separately so the Player Pool mirrors how the field actually builds.
        # Prefer field ownership saved for the active format. If that table is missing,
        # rebuild it directly from the current simulated opponent field so the Player Pool
        # always shows field ownership after CONTEST SIM.
        _ownership_by_format = st.session_state.get("latest_field_ownership_by_format", {})
        field_ownership_display = (
            _ownership_by_format.get(selected_format)
            if isinstance(_ownership_by_format, dict)
            else None
        )
        if not isinstance(field_ownership_display, pd.DataFrame) or field_ownership_display.empty:
            field_ownership_display = st.session_state.get("latest_field_ownership")

        if not isinstance(field_ownership_display, pd.DataFrame) or field_ownership_display.empty:
            if platform == "DraftKings" and lineup_mode == "Showdown":
                _active_field = st.session_state.get("contest_field_df")
                _role_col = "Captain"
                _field_slots = [c for c in ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"] if isinstance(_active_field, pd.DataFrame) and c in _active_field.columns]
            else:
                _active_field = st.session_state.get("classic_contest_field_df")
                _role_col = None
                _field_slots = [c for c in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"] if isinstance(_active_field, pd.DataFrame) and c in _active_field.columns]

            if isinstance(_active_field, pd.DataFrame) and not _active_field.empty and _field_slots:
                _field_total = len(_active_field)
                _all_counts = (
                    _active_field[_field_slots]
                    .astype(str)
                    .apply(lambda row: pd.unique(row.str.strip()).tolist(), axis=1)
                    .explode()
                    .value_counts()
                )
                _field_names = player_display["Name"].astype(str).str.strip()
                field_ownership_display = pd.DataFrame({
                    "Name": _field_names,
                    "Ownership %": _field_names.map(lambda n: 100.0 * _all_counts.get(n, 0) / max(_field_total, 1)),
                })
                if _role_col is not None and _role_col in _active_field.columns:
                    _role_counts = _active_field[_role_col].astype(str).str.strip().value_counts()
                    field_ownership_display["Captain/MVP Ownership %"] = _field_names.map(
                        lambda n: 100.0 * _role_counts.get(n, 0) / max(_field_total, 1)
                    )
                if not isinstance(_ownership_by_format, dict):
                    _ownership_by_format = {}
                _ownership_by_format[selected_format] = field_ownership_display.copy()
                st.session_state["latest_field_ownership_by_format"] = _ownership_by_format
                st.session_state["latest_field_ownership"] = field_ownership_display.copy()

        if (
            isinstance(field_ownership_display, pd.DataFrame)
            and not field_ownership_display.empty
            and "Name" in field_ownership_display.columns
            and "Ownership %" in field_ownership_display.columns
        ):
            field_own_map = dict(zip(
                field_ownership_display["Name"].astype(str).str.strip(),
                pd.to_numeric(field_ownership_display["Ownership %"], errors="coerce")
            ))
            names_for_field = player_display["Name"].astype(str).str.strip()
            overall_field = names_for_field.map(field_own_map)
            player_display["Field Own %"] = overall_field.round(1)
            if platform == "DraftKings" and lineup_mode == "Showdown":
                if "Captain/MVP Ownership %" in field_ownership_display.columns:
                    field_captain_map = dict(zip(
                        field_ownership_display["Name"].astype(str).str.strip(),
                        pd.to_numeric(field_ownership_display["Captain/MVP Ownership %"], errors="coerce")
                    ))
                    captain_field = names_for_field.map(field_captain_map).fillna(0.0)
                else:
                    captain_field = pd.Series(0.0, index=player_display.index)
                player_display["Field CPT Own %"] = captain_field.round(1)
                player_display["Field FLEX Own %"] = (overall_field.fillna(0.0) - captain_field).clip(lower=0.0).round(1)
                player_display = player_display.drop(columns=["Field Own %"], errors="ignore")
            else:
                player_display["Field Own %"] = overall_field.round(1)
                player_display = player_display.drop(columns=["Field CPT Own %", "Field FLEX Own %"], errors="ignore")
        else:
            player_display["Field Own %"] = np.nan
            if platform == "DraftKings" and lineup_mode == "Showdown":
                player_display["Field CPT Own %"] = np.nan
                player_display["Field FLEX Own %"] = np.nan
                player_display = player_display.drop(columns=["Field Own %"], errors="ignore")
            else:
                player_display["Field Own %"] = np.nan
                player_display = player_display.drop(columns=["Field CPT Own %", "Field FLEX Own %"], errors="ignore")

        # Use the active format's saved FanDuel PBP outcomes. The generic simulation_df
        # belongs to the DraftKings/shared path and can be stale or absent on FanDuel.
        _active_simulation_df = None
        if platform == "FanDuel":
            _fd_pool_sim_key = "fd_simulation_df_" + lineup_mode.replace(" ", "_").lower()
            _fd_saved_sim = st.session_state.get(_fd_pool_sim_key)
            if isinstance(_fd_saved_sim, pd.DataFrame) and not _fd_saved_sim.empty:
                _active_simulation_df = _fd_saved_sim
        elif isinstance(st.session_state.get("simulation_df"), pd.DataFrame):
            _active_simulation_df = st.session_state.get("simulation_df")

        if isinstance(_active_simulation_df, pd.DataFrame):
            simulation_df = _active_simulation_df

            # IMPORTANT: simulation_df can be retained in Streamlit session state while
            # the user changes slate, site, or player pool. Never assign its columns to
            # the current player list by position: that can attach one player's outcome
            # distribution (for example, a high-scoring QB) to a completely different
            # player. Join every summary by the player name used as the simulation column.
            if isinstance(simulation_df, pd.DataFrame) and not simulation_df.empty:
                simulation_means = simulation_df.mean(axis=0)
                player_display["SimMean"] = player_display["Name"].astype(str).str.strip().map(
                    {str(k).strip(): v for k, v in simulation_means.items()}
                )
                for quantile, column in [
                    (0.10, "SimP10"), (0.25, "SimP25"), (0.50, "SimP50"),
                    (0.75, "SimP75"), (0.90, "SimP90"), (0.95, "SimP95"),
                    (0.99, "SimP99")
                ]:
                    summary = simulation_df.quantile(quantile, axis=0)
                    player_display[column] = player_display["Name"].astype(str).str.strip().map(
                        {str(k).strip(): v for k, v in summary.items()}
                    )
                cap_hit_map = st.session_state.get("simulation_cap_hit_pct", {})
                player_display["Cap Hit %"] = player_display["Name"].astype(str).str.strip().map(
                    {str(k).strip(): v for k, v in cap_hit_map.items()}
                )
            else:
                for column in [
                    "SimMean", "SimP10", "SimP25", "SimP50",
                    "SimP75", "SimP90", "SimP95", "SimP99"
                ]:
                    player_display[column] = np.nan
                player_display["Cap Hit %"] = np.nan
        else:
            for column in [
                "SimMean",
                "SimP10",
                "SimP25",
                "SimP50",
                "SimP75",
                "SimP90",
                "SimP95",
                "SimP99"
            ]:
                player_display[column] = np.nan
            player_display["Cap Hit %"] = np.nan

        # Make the main simulated average easy to spot in the Player Pool.
        # "Sim Pts" is the average fantasy score across the configured simulated outcomes.
        player_display = player_display.rename(columns={
            "SimMean": "Sim Pts",
            "SimP10": "Sim P10",
            "SimP25": "Sim P25",
            "SimP50": "Sim P50",
            "SimP75": "Sim P75",
            "SimP90": "Sim P90",
            "SimP95": "Sim P95",
            "SimP99": "Sim P99",
        })
        for sim_column in [
            "Sim Pts", "Sim P10", "Sim P25", "Sim P50",
            "Sim P75", "Sim P90", "Sim P95", "Sim P99", "Cap Hit %"
        ]:
            player_display[sim_column] = pd.to_numeric(
                player_display[sim_column], errors="coerce"
            ).round(1)

        # Show editable player settings in their own block, separate from player stats.
        existing_control_values = st.session_state.get("control_values")
        if existing_control_values is not None:
            existing_control_values = existing_control_values.drop_duplicates("Name").set_index("Name")

        # Combine player details, simulated stats, realized exposure, and editable controls
        # into one table so exposure is visible beside the limits you can change.
        from simmah_player_display import complete_player_display
        player_display = complete_player_display(
            player_display, st.session_state.get("simulation_df"),
            st.session_state.get("classic_contest_entries_df", st.session_state.get("classic_lineups")) if lineup_mode == "Classic" else st.session_state.get("portfolio_df"),
            st.session_state.get("classic_contest_field_df") if lineup_mode == "Classic" else st.session_state.get("contest_field_df"),
            st.session_state.get("classic_ownership_snapshot") if lineup_mode == "Classic" else None,
        )
        from simmah_leverage import attach_leverage
        player_display = attach_leverage(player_display, leverage_opportunities_cached(
            st.session_state.get("simulation_df"),
            st.session_state.get("classic_lineups") if lineup_mode == "Classic" else st.session_state.get("candidates_df")))
        st.caption("Leverage (pp) = candidate-best selection share minus projected ownership, or simulated-field ownership when projections are unavailable. Positive values suggest underownership within this candidate set, not guaranteed profit. CPT/MVP and FLEX leverage use separate simulated-field ownership. Values fill after SIM, BUILD and field generation.")
        st.caption("Simulation and ownership summaries fill after SIM completes. Pending values are not zero; unavailable weather is shown explicitly.")
        control_display = player_display.copy()
        for required_column in ["Name", "Position", "Team", "Opponent"]:
            if required_column not in control_display.columns:
                control_display[required_column] = players_df[required_column].values
        display_settings = [
            ("Lock", False),
            ("Min Exposure %", 0), ("Max Exposure %", 100)
        ]
        # Captain exposure limits belong only to Showdown formats.
        if not (platform == "DraftKings" and lineup_mode == "Classic"):
            display_settings.extend([
                ("Captain Min %", 0), ("Captain Max %", 100)
            ])
        for setting, default in display_settings:
            if existing_control_values is not None and setting in existing_control_values.columns:
                control_display[setting] = control_display["Name"].map(existing_control_values[setting]).fillna(default)
            else:
                control_display[setting] = default

        from simmah_leverage import add_value_columns
        control_display = add_value_columns(control_display)
        if isinstance(_active_simulation_df, pd.DataFrame) and not _active_simulation_df.empty:
            save_automatic_pregame_snapshot(
                control_display,
                selected_format,
                correlation_pct=float(correlation_strength) * 100.0,
                aggressiveness_pct=float(aggressiveness) * 100.0,
            )

        # Keep the visible Player Pool compact and in a consistent left-to-right order.
        # ProjectionSource and Injury Status still remain in the underlying data for app logic.
        # Keep source, injury status, and Fade visible as shown in the requested Player Pool layout.
        control_display = control_display.drop(columns=["CaptainSalary"], errors="ignore")
        _preferred_player_pool_order = [
            "Name", "Position", "Team", "Opponent", "Salary",
            "Projection", "Sim Pts", "ProjectionSource", "Injury Status",
            "Captain Exp %", "MVP Exp %", "Exposure %", "Flex Exp %",
            "Projected Own %", "Mine Own %",
            "Field CPT Own %", "Field MVP Own %", "Field FLEX Own %", "Field Own %",
            "Sim P10", "Sim P25", "Sim P50", "Sim P75", "Sim P90", "Sim P95", "Sim P99",
            "Cap Hit %", "Lock", "Fade",
            "Min Exposure %", "Max Exposure %", "Captain Min %", "Captain Max %",
        ]
        _ordered_player_pool_columns = [
            column for column in _preferred_player_pool_order if column in control_display.columns
        ]
        _remaining_player_pool_columns = [
            column for column in control_display.columns
            if column not in _ordered_player_pool_columns
        ]
        control_display = control_display[_ordered_player_pool_columns + _remaining_player_pool_columns]

        st.caption("Player stats, simulation results, exposure, and editable controls are all in this one table. Lock includes a player.")
        editable_control_columns = [setting for setting, _ in display_settings]
        disabled_control_columns = [
            column for column in control_display.columns
            if column not in editable_control_columns
        ]
        _dk_show_all_columns = st.checkbox("Show all player columns", value=False,
            key="dk_show_all_player_columns_" + lineup_mode.replace(" ", "_").lower())
        control_display = injury_player_pool(control_display)
        disabled_control_columns.append("Player")
        edited_player_controls = st.data_editor(
            control_display,
            use_container_width=True,
            hide_index=True,
            column_order=None if _dk_show_all_columns else player_columns(control_display),
            row_height=32,
            height=660,
            disabled=disabled_control_columns,
            column_config={
                **player_column_config(st),
                "Name": st.column_config.TextColumn("Name"),
                "Player": st.column_config.TextColumn("Player", pinned=True),
                "Lock": st.column_config.CheckboxColumn("Lock", help="Force this player into lineup builds."),
                "Min Exposure %": st.column_config.NumberColumn("Min Exp %", min_value=0, max_value=100, step=5, format="%d%%"),
                "Max Exposure %": st.column_config.NumberColumn("Max Exp %", min_value=0, max_value=100, step=5, format="%d%%"),
                "Captain Min %": st.column_config.NumberColumn("CPT Min %", min_value=0, max_value=100, step=5, format="%d%%"),
                "Captain Max %": st.column_config.NumberColumn("CPT Max %", min_value=0, max_value=100, step=5, format="%d%%"),
            },
            key="player_controls_editor"
        )

        # Keep the player stats table read-only; settings are changed in the block above.
        player_display = player_display[
            [c for c in player_display.columns if c not in [
                "Lock", "Fade", "Min Exposure %", "Max Exposure %",
                "Captain Min %", "Captain Max %"
            ]]
        ]
        # Captain exposure is only relevant to DraftKings Showdown.
        if platform == "DraftKings" and lineup_mode == "Classic":
            player_display = player_display.drop(columns=["Captain Exp %"], errors="ignore")
        # Export pre-game projections so they can be matched to actual scores later.
        with st.expander("Save Pre-Game Projection Snapshot", expanded=False):
            st.caption(
                "The app now automatically saves the latest pregame snapshot after SIM. "
                "This download is only an extra backup copy."
            )
            snapshot_date = st.date_input(
                "Game date for this snapshot",
                value=pd.Timestamp.now(tz=ZoneInfo("America/New_York")).date(),
                key="projection_snapshot_game_date",
            )
            snapshot_columns = [
                c for c in [
                    "Name", "Position", "Team", "Opponent", "Salary", "DK_ID",
                    "Projection", "ProjectionSource", "Injury Status"
                ] if c in players_df.columns
            ]
            snapshot_df = players_df[snapshot_columns].copy()
            snapshot_df.insert(0, "GameDate", str(snapshot_date))
            snapshot_df.insert(1, "Format", selected_format)
            st.download_button(
                "Download Pre-Game Projection Snapshot",
                data=snapshot_df.to_csv(index=False).encode("utf-8"),
                file_name=f"projection_snapshot_{selected_format.lower().replace(' ', '_')}_{snapshot_date}.csv",
                mime="text/csv",
                key="projection_snapshot_download",
            )


        # Keep the Lock/Fade selections from the Player Pool editor and preserve
        # the existing exposure controls internally at their saved/default values.
        existing_controls = st.session_state.get("control_values")
        if existing_controls is not None:
            previous_by_name = existing_controls.drop_duplicates("Name").set_index("Name")
            control_values = players_df[["Name", "Position", "Team", "Opponent"]].copy()
            for setting, default in [
                ("Lock", False), ("Fade", False),
                ("Min Exposure %", 0), ("Max Exposure %", 100),
                ("Captain Min %", 0), ("Captain Max %", 100)
            ]:
                if setting in previous_by_name.columns:
                    control_values[setting] = control_values["Name"].map(previous_by_name[setting]).fillna(default)
                else:
                    control_values[setting] = default
        else:
            control_values = players_df[["Name", "Position", "Team", "Opponent"]].copy()
            control_values["Lock"] = False
            control_values["Fade"] = False
            control_values["Min Exposure %"] = 0
            control_values["Max Exposure %"] = 100
            control_values["Captain Min %"] = 0
            control_values["Captain Max %"] = 100

        editor_controls = edited_player_controls.set_index("Name")
        for setting in [
            "Lock", "Min Exposure %", "Max Exposure %"
        ] + (
            [] if platform == "DraftKings" and lineup_mode == "Classic"
            else ["Captain Min %", "Captain Max %"]
        ):
            control_values[setting] = control_values["Name"].map(
                editor_controls[setting]
            ).fillna(control_values[setting])
        control_values["Lock"] = control_values["Lock"].astype(bool)
        control_values["Fade"] = False
        for setting in ["Min Exposure %", "Max Exposure %", "Captain Min %", "Captain Max %"]:
            control_values[setting] = pd.to_numeric(control_values[setting], errors="coerce").fillna(
                0 if "Min" in setting else 100
            ).clip(0, 100)
        st.session_state["control_values"] = control_values
        edited_controls = control_values.copy()
        control_map = edited_controls.set_index("Name").to_dict("index")
        available_players = [
            p for p in players_df["Name"]
            if p in control_map and not control_map[p]["Fade"]
        ]

        # ============================================
        # SALARY MAPS
        # ============================================

        salary_map = dict(zip(
            players_df["Name"],
            players_df["Salary"]
        ))

        captain_salary_map = dict(zip(
            players_df["Name"],
            players_df["CaptainSalary"]
        ))

        # SIMULATION VALUES
        # ============================================

        player_sim = {}

        if isinstance(_active_simulation_df, pd.DataFrame) and not _active_simulation_df.empty:
            simulation_df = _active_simulation_df

            for player in players_df["Name"]:
                if player in simulation_df.columns:
                    values = simulation_df[player]
                    player_sim[player] = {
                        "Mean": values.mean(),
                        "P95": values.quantile(0.95),
                        "P99": values.quantile(0.99),
                    "StdDev": values.std(ddof=0)
                    }

        # Safe fallback so the page can render before the first simulation.
        for _, player_row in players_df.iterrows():
            player = player_row["Name"]
            if player not in player_sim:
                projection = max(float(player_row["Projection"]), 0.01)
                player_sim[player] = {
                    "Mean": projection,
                    "P95": projection * 1.8,
                    "P99": projection * 2.3,
                    "StdDev": 0.0
                }

    # ============================================
    # DRAFTKINGS CLASSIC BUILDER
    # ============================================

    with _tab_build:
        if platform == "DraftKings" and lineup_mode == "Classic":
            render_saved_market_calibration(platform, lineup_mode, players_df)
            st.write("### DraftKings Classic Lineups")
            st.caption(
                "Classic roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), DST. "
                "Salary cap: $50,000. SIM uses the shared NFL play-by-play engine so every lineup is scored against the same correlated game outcomes. "
                "The 5,000-lineup build automatically spreads exposure instead of repeatedly selecting the same top players."
            )

            def classic_positions(value):
                raw = str(value).upper().replace(" ", "")
                return set(raw.split("/"))

            classic_pool = players_df.copy()
            classic_pool["Eligible"] = classic_pool["Position"].apply(classic_positions)
            classic_pool = classic_pool[
                classic_pool["Name"].isin(available_players)
                & (classic_pool["Salary"] > 0)
            ].copy()

            roster_slots = [
                ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}), ("DST", {"DST"})
            ]

            build_cols = [_build_controls.container() for _ in range(3)]
            with build_cols[0]:
                st.write("### Build Settings")
                dk_salary_range = st.slider(
                    "Allowed lineup salary range",
                    min_value=0,
                    max_value=50000,
                    value=(48000, 50000),
                    step=100,
                    format="$%d",
                    key="dk_build_salary_range_" + lineup_mode.replace(" ", "_").lower() + "_48000",
                    help="Only build lineups whose total salary falls inside this range."
                )
            MIN_LINEUP_SALARY, MAX_LINEUP_SALARY = dk_salary_range
            with build_cols[1]:
                portfolio_diversity, aggressiveness = render_diversity_controls(st, platform, lineup_mode, SIMULATION_COUNT)

            with _build_controls:
                dk_classic_stack_rules = st.multiselect(
                    "Stacks to use in MY lineups",
                    BUILD_STACK_OPTIONS,
                    default=[ANY_STACK_OPTION],
                    key="dk_classic_stack_rules_v2",
                    help="Any / All allows every primary structure, including unstacked lineups, and takes precedence over other primary choices. No stack requires zero same-team WR/TE with your QB. Otherwise, accept any selected structure. Optional secondary rules still apply. Clear selections also allows any structure.",
                )
                dk_secondary_stack_rules = st.multiselect(
                    "Optional secondary stacks",
                    SECONDARY_STACK_OPTIONS,
                    default=[],
                    key="dk_classic_stack_rules_secondary_v2",
                    help="Each selected secondary rule is required in addition to a selected QB stack. Mini-stacks use another game.",
                )
                st.caption("Choose your DraftKings Classic stack rules before pressing BUILD.")

            # Real DraftKings Classic main-slate contests supplied by the user.
            # Each payout tuple is (first_place, last_place, prize_dollars).
            with _contest_setup:
                CLASSIC_CONTESTS = {
                    "NFL $4K Dime Package [Just $0.10!]": {"entry": 0.10, "field": 47500, "max_entries": 20, "prize_pool": 4000, "payouts": [(1,1,200),(2,2,150),(3,3,100),(4,4,75),(5,5,60),(6,6,50),(7,7,40),(8,8,30),(9,9,25),(10,10,20),(11,15,15),(16,20,10),(21,25,8),(26,30,6),(31,40,5),(41,50,4),(51,65,3),(66,85,2),(86,110,1.5),(111,155,1),(156,275,.75),(276,585,.50),(586,1385,.40),(1386,3670,.30),(3671,11405,.20)]},
                    "NFL $15K Quarter Jukebox [Just $0.25!]": {"entry": .25, "field": 71300, "max_entries": 20, "prize_pool": 15000, "payouts": [(1,1,750),(2,2,500),(3,3,300),(4,4,200),(5,5,150),(6,7,100),(8,10,75),(11,15,50),(16,20,40),(21,25,30),(26,30,25),(31,40,20),(41,50,15),(51,65,10),(66,85,8),(86,110,6),(111,140,5),(141,180,4),(181,240,3),(241,425,2),(426,845,1.5),(846,2105,1),(2106,5635,.75),(5636,17120,.50)]},
                    "NFL $175K mini-MAX [150 Entry Max]": {"entry": .50, "field": 416100, "max_entries": 150, "prize_pool": 175000, "payouts": [(1,1,20000),(2,2,7500),(3,3,3000),(4,4,2000),(5,5,1500),(6,6,1000),(7,8,750),(9,10,600),(11,12,500),(13,15,400),(16,19,300),(20,24,250),(25,30,200),(31,40,150),(41,50,100),(51,65,75),(66,85,60),(86,110,50),(111,140,40),(141,180,30),(181,230,25),(231,290,20),(291,370,15),(371,490,10),(491,640,8),(641,840,6),(841,1615,5),(1616,3120,4),(3121,6270,3),(6271,14035,2),(14036,29015,1.5),(29016,87395,1)]},
                    "NFL $4K Mini First Down": {"entry": 1, "field": 4756, "max_entries": 20, "prize_pool": 4000, "payouts": [(1,1,400),(2,2,200),(3,3,150),(4,4,100),(5,5,80),(6,6,70),(7,7,60),(8,8,50),(9,10,40),(11,15,30),(16,20,20),(21,25,15),(26,35,10),(36,50,8),(51,80,6),(81,150,4),(151,300,3),(301,601,2),(602,1103,1.5)]},
                    "NFL $2.75M Fantasy Football Millionaire": {"entry": 20, "field": 161700, "max_entries": 150, "prize_pool": 2750000, "payouts": [(1,1,1000000),(2,2,100000),(3,3,50000),(4,4,25000),(5,5,15000),(6,6,10000),(7,8,7000),(9,10,5000),(11,15,3000),(16,20,2000),(21,30,1500),(31,45,1000),(46,65,700),(66,95,500),(96,135,400),(136,195,300),(196,315,200),(316,515,150),(516,1025,100),(1026,2425,70),(2426,5925,50),(5926,14425,40),(14426,37425,30)]},
                    "NFL $600K Play-Action [20 Entry Max]": {"entry": 3, "field": 237800, "max_entries": 20, "prize_pool": 600000, "payouts": [(1,1,50000),(2,2,25000),(3,3,15000),(4,4,10000),(5,5,7500),(6,6,5000),(7,8,3000),(9,10,2000),(11,15,1500),(16,20,1000),(21,30,750),(31,40,500),(41,50,300),(51,75,200),(76,100,150),(101,150,100),(151,250,75),(251,350,60),(351,550,50),(551,750,40),(751,1000,30),(1001,1500,20),(1501,2500,15),(2501,4000,12),(4001,6500,10),(6501,10000,9),(10001,15000,8),(15001,25000,7),(25001,39000,6),(39001,59650,5)]},
                    "NFL $400K Flea Flicker [$50K to 1st]": {"entry": 5, "field": 95100, "max_entries": 150, "prize_pool": 400000, "payouts": [(1,1,50000),(2,2,25000),(3,3,15000),(4,4,10000),(5,5,7000),(6,6,5000),(7,8,3000),(9,10,2000),(11,15,1500),(16,20,1000),(21,25,700),(26,30,500),(31,40,300),(41,50,200),(51,75,150),(76,100,100),(101,150,75),(151,250,50),(251,450,35),(451,850,25),(851,1600,20),(1601,3100,15),(3101,6100,12),(6101,12400,10),(12401,23150,8)]},
                    "NFL $100K First Down [20 Entry Max]": {"entry": 1, "field": 118900, "max_entries": 20, "prize_pool": 100000, "payouts": [(1,1,5000),(2,2,2500),(3,3,1500),(4,4,1000),(5,5,750),(6,7,600),(8,10,500),(11,14,400),(15,19,300),(20,25,250),(26,35,200),(36,45,150),(46,60,100),(61,80,75),(81,105,60),(106,135,50),(136,175,40),(176,225,30),(226,285,25),(286,360,20),(361,460,15),(461,610,10),(611,800,8),(801,1085,6),(1086,1665,5),(1666,3005,4),(3006,6110,3),(6111,13242,2),(13243,32096,1.5)]},
                    "NFL $50K MEGA mini-MAX [150 Entry Max]": {"entry": 2, "field": 29700, "max_entries": 150, "prize_pool": 50000, "payouts": [(1,1,5000),(2,2,2500),(3,3,1000),(4,4,600),(5,5,500),(6,6,400),(7,8,300),(9,10,250),(11,14,200),(15,20,150),(21,30,100),(31,40,75),(41,55,60),(56,70,50),(71,90,40),(91,115,30),(116,145,25),(146,185,20),(186,235,15),(236,385,10),(386,700,8),(701,1325,6),(1326,2525,5),(2526,6570,4)]},
                    "NFL $40K Front Four [20 Entry Max]": {"entry": 4, "field": 11800, "max_entries": 20, "prize_pool": 40000, "payouts": [(1,1,4000),(2,2,2000),(3,3,1500),(4,4,1000),(5,5,750),(6,6,600),(7,8,500),(9,10,400),(11,12,300),(13,14,250),(15,16,200),(17,21,150),(22,26,100),(27,31,75),(32,36,60),(37,46,50),(47,56,40),(57,71,30),(72,96,25),(97,151,20),(152,291,15),(292,661,10),(662,1396,8),(1397,3091,6)]},
                    "NFL $20K Safety [20 Entry Max]": {"entry": 2, "field": 11800, "max_entries": 20, "prize_pool": 20000, "payouts": [(1,1,1000),(2,2,600),(3,3,400),(4,4,300),(5,5,250),(6,7,200),(8,10,150),(11,15,100),(16,20,75),(21,30,60),(31,40,50),(41,50,40),(51,65,30),(66,85,25),(86,110,20),(111,140,15),(141,190,10),(191,295,8),(296,515,6),(516,930,5),(931,1680,4),(1681,3210,3)]},
                }
                classic_contest_name = st.selectbox(
                    "Classic contest for CONTEST SIM", list(CLASSIC_CONTESTS),
                    key="dk_classic_contest_name"
                )
                classic_contest = CLASSIC_CONTESTS[classic_contest_name]
                classic_entry_count = st.number_input(
                    "My entries in this Classic contest", min_value=1,
                    max_value=int(classic_contest["max_entries"]),
                    value=int(classic_contest["max_entries"]), step=1,
                    key="dk_classic_contest_entry_count"
                )
                st.caption(
                    f"${classic_contest['entry']:.2f} entry · {classic_contest['field']:,} max field · "
                    f"${classic_contest['prize_pool']:,.0f} prizes · {classic_contest['max_entries']} entry max"
                )

            with build_cols[2]:
                st.write("### Run")
                _classic_sim_button = st.button(
                    "SIM", type="primary", use_container_width=True, key="dk_classic_sim"
                )
                # One-click Classic workflow: SIM -> BUILD -> CONTEST SIM -> ROI.
                _classic_build_button = _classic_sim_button
                _classic_contest_button = _classic_sim_button
                classic_run_all = _classic_sim_button
            classic_workflow_status = None
            if _classic_sim_button or _classic_build_button:
                classic_workflow_status = st.empty()
                classic_workflow_status.info(
                    f"Step 1 of 4: Running {SIMULATION_COUNT:,} player simulations for DraftKings Classic..."
                )
                try:
                    classic_simulation_df = run_game_simulations(
                        players_df, platform=platform, workflow_status=classic_workflow_status
                    )
                    if not isinstance(classic_simulation_df, pd.DataFrame) or classic_simulation_df.empty:
                        raise RuntimeError("The player simulation returned no results.")
                    st.session_state["simulation_df"] = classic_simulation_df
                    st.session_state["simulations_ready"] = True

                    # Build ranking statistics from this click's simulation results, not stale values.
                    player_sim = {}
                    missing_names = [
                        str(name) for name in classic_pool["Name"]
                        if name not in classic_simulation_df.columns
                    ]
                    if missing_names:
                        raise RuntimeError(
                            "Simulation results are missing player columns: "
                            + ", ".join(missing_names[:10])
                        )
                    for name in classic_pool["Name"].astype(str):
                        values = pd.to_numeric(classic_simulation_df[name], errors="coerce").dropna()
                        if values.empty:
                            raise RuntimeError(f"No usable simulated scores were returned for {name}.")
                        player_sim[name] = {
                            "Mean": float(values.mean()),
                            "P95": float(values.quantile(0.95)),
                            "P99": float(values.quantile(0.99)),
                            "StdDev": float(values.std(ddof=0)),
                        }
                    classic_workflow_status.info(
                        "Step 2 of 4: Preparing rankings and building your candidate lineups..."
                    )
                except Exception as exc:
                    classic_workflow_status.error(
                        f"SIM stopped during player simulations or ranking setup: {type(exc).__name__}: {exc}"
                    )
                    st.exception(exc)
                    workspace_stop(st, _loaded_slate_tabs)

            build_clicked = _classic_build_button

            if build_clicked and platform == "DraftKings" and lineup_mode == "Classic":
                for _classic_old_key in ("classic_lineups", "classic_contest_comparison_df", "classic_contest_entries_df", "classic_contest_field_df", "classic_contest_field_ready", "classic_field_context"):
                    st.session_state.pop(_classic_old_key, None)
                classic_locked_players = [name for name in available_players if control_map.get(name, {}).get("Lock", False)]
                try:
                    classic_results = build_joint_candidate_pool(classic_pool.reset_index(drop=True), "DraftKings", "Classic",
                        st.session_state["simulation_df"], roster_slots, MIN_LINEUP_SALARY, min(MAX_LINEUP_SALARY, 50000),
                        locks=classic_locked_players, selected_stacks=dk_classic_stack_rules,
                        secondary_stacks=dk_secondary_stack_rules, aggressiveness=aggressiveness)
                    st.session_state["classic_lineups"] = classic_results
                    st.session_state["classic_pool_signature"] = slate_signature
                except Exception as exc:
                    st.error(f"DraftKings Classic candidate build stopped: {exc}")
                    workspace_stop(st, _loaded_slate_tabs)

            if _classic_contest_button and platform == "DraftKings" and lineup_mode == "Classic":
                # Keep the Classic workflow compact, matching the single-button Showdown layout.
                if "simulation_df" not in st.session_state:
                    st.warning("Run SIM first, then run CONTEST SIM.")
                elif len(classic_pool) < 9:
                    st.error("At least 9 eligible players are required for DraftKings Classic Contest Sim.")
                elif st.session_state.get("classic_lineups") is None:
                    st.warning("Click BUILD first so CONTEST SIM can test your lineups.")
                else:
                    if dk_opponent_target <= 0:
                        st.warning("Total contest entries must be greater than your own entries.")
                    with st.spinner(f"Testing your lineups against {dk_opponent_target:,} simulated contest entries..."):
                        rng = np.random.default_rng()
                        sim_df = st.session_state["simulation_df"]
                        mean_scores = sim_df.mean(axis=0).to_dict()
                        pool = classic_pool.copy()
                        pool["MeanPoints"] = pool["Name"].map(mean_scores).fillna(pool["Projection"])
                        pool = attach_main_slate_ownership(pool, "draftkings")
                        ownership_columns = [c for c in ["Name", "Team", "Opponent", "Position", "Salary", "Projected Ownership", "Ownership Source", "Ownership Updated UTC", "Ownership Week", "Ownership Selection Weight"] if c in pool.columns]
                        pool["Weight"] = opponent_field_selection_weights(
                            pool, pool["MeanPoints"].to_numpy(dtype=float)
                        )
                        if "Ownership Source" not in pool.columns:
                            pool["Ownership Source"] = "Uploaded ownership" if "Projected Ownership" in pool.columns else "Projection-rank popularity fallback (no external ownership)"
                        pool["Opponent Selection Weight"] = pool["Weight"]
                        ownership_columns = list(dict.fromkeys(ownership_columns + ["Ownership Source", "Opponent Selection Weight"]))
                        st.session_state["classic_ownership_snapshot"] = pool[ownership_columns].copy()
                        contest_slots = [
                            ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                            ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                            ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}), ("DST", {"DST"})
                        ]
                        from simmah_classic_field import build_full_roster_field
                        field_slot_names = [slot for slot, _ in contest_slots]
                        field_target = learned_field_proposal_target("DraftKings", "Classic", classic_contest, 9, ownership_proposal_target(pool, "Classic", dk_opponent_target), pool)
                        _classic_field_progress = st.progress(0, text=f"Building DraftKings opponent field: 0 / {field_target:,}")
                        contest_field_df = build_full_roster_field(pool, pool["Weight"].to_numpy(float), field_slot_names,
                            field_target, rng=rng, platform="DraftKings",
                            construction_distribution=opponent_construction_distribution("DraftKings", "Classic", classic_contest, pool),
                            progress=lambda fraction,text: _classic_field_progress.progress(fraction,text=text))
                        _classic_field_progress.empty()
                        contest_field_df = apply_learned_field(contest_field_df, pool, field_slot_names, "DraftKings", "Classic", classic_contest, int(dk_opponent_target), rng)
                        st.caption("Opponent construction uses matching completed-contest stack/bring-back frequencies when available; otherwise the baseline requires a QB + WR/TE stack. Field popularity uses external ownership when available, otherwise estimated popularity.")
                        user_lineups = st.session_state["classic_lineups"].copy()
                        opponent_scores = contest_field_df["ProjectedPoints"].to_numpy(dtype=float) if not contest_field_df.empty else np.array([])
                        if len(opponent_scores):
                            user_lineups = add_lineup_field_ownership(user_lineups)
                            _opp_sorted_static = np.sort(opponent_scores)
                            _user_static = user_lineups["ProjectedPoints"].to_numpy(dtype=float)
                            _less_static = np.searchsorted(_opp_sorted_static, _user_static, side="left")
                            _right_static = np.searchsorted(_opp_sorted_static, _user_static, side="right")
                            user_lineups["BeatsOpponents"] = _less_static
                            user_lineups["FieldPercentile"] = np.round(100.0 * _right_static / len(_opp_sorted_static), 1)
                            user_lineups["FieldRank"] = 1 + len(_opp_sorted_static) - _right_static
                            user_lineups = add_field_ranking_metrics(user_lineups, opponent_scores)
                            # Convert representative-field percentile to the selected contest's
                            # full-field rank, then apply its exact payout ladder.
                            full_field_size = int(classic_contest["field"])
                            user_lineups["Estimated Full Field Rank"] = user_lineups["FieldPercentile"].apply(
                                lambda pct: max(1, min(full_field_size, int(np.ceil((1.0 - float(pct) / 100.0) * full_field_size))))
                            )
                            def _classic_prize(rank):
                                for first, last, prize in classic_contest["payouts"]:
                                    if int(first) <= int(rank) <= int(last):
                                        return float(prize)
                                return 0.0
                            from simmah_contests import evaluate_contest
                            _classic_progress = st.progress(0, text="Scoring DraftKings Classic contest outcomes...")
                            _classic_slots = [slot for slot, _ in contest_slots]
                            user_lineups = evaluate_contest(sim_df, user_lineups, contest_field_df, _classic_slots,
                                full_field_size, classic_contest["payouts"], float(classic_contest["entry"]),
                                progress=lambda fraction,text: _classic_progress.progress(fraction,text=text))
                            st.caption(f"Contest evaluation used all {len(sim_df):,} independent evaluation outcomes. Opponents are a representative estimated field; tied prizes are split across all occupied payout places.")
                            _classic_progress.empty()
                        st.session_state["classic_contest_field_df"] = contest_field_df
                        st.session_state["classic_contest_field_ready"] = len(contest_field_df) > 0
                        st.session_state["classic_contest_comparison_df"] = user_lineups
                        st.session_state["classic_field_context"] = classic_contest_name
                    if not contest_field_df.empty:
                        st.success(f"Compared your {len(user_lineups)} lineups against {len(contest_field_df):,} simulated opponent lineups.")
                        st.write("### Your Lineups vs. Contest Field")
                        st.caption("Contest metrics use all independent evaluation outcomes against an estimated opponent field and the selected payout ladder.")
                        st.dataframe(injury_frame(st, user_lineups), use_container_width=True, hide_index=True)
                        st.metric("Simulated opponent lineups", f"{len(contest_field_df):,}")
                        if all(c in user_lineups.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                            _classic_sanity = pd.DataFrame([{
                                "Top 1%": round(100 * float(user_lineups["Top1"].mean()), 2),
                                "Top 5%": round(100 * float(user_lineups["Top5"].mean()), 2),
                                "Top 10%": round(100 * float(user_lineups["Top10"].mean()), 2),
                                "Cash %": round(100 * float(user_lineups["CashRate"].mean()), 2),
                            }])
                            st.write("### Field Sanity Check")
                            st.dataframe(injury_frame(st, _classic_sanity), use_container_width=True, hide_index=True)
                        # Field ownership is already shown in the Player Pool.
                    else:
                        st.error("Could not create valid opponent lineups. Check the player pool and salary range.")
            # Redisplay the last completed Classic Contest Sim after widget changes
            # such as changing the Portfolio count or ranking method.
            if not _classic_contest_button:
                _saved_classic_comparison = st.session_state.get("classic_contest_comparison_df")
                _saved_classic_field = st.session_state.get("classic_contest_field_df")
                if isinstance(_saved_classic_comparison, pd.DataFrame) and not _saved_classic_comparison.empty:
                    st.write("### Your Lineups vs. Contest Field")
                    st.dataframe(injury_frame(st, _saved_classic_comparison), use_container_width=True, hide_index=True)
                    if isinstance(_saved_classic_field, pd.DataFrame) and not _saved_classic_field.empty:
                        st.metric("Simulated opponent lineups", f"{len(_saved_classic_field):,}")
                    if all(c in _saved_classic_comparison.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                        _saved_classic_sanity = pd.DataFrame([{
                            "Top 1%": round(100 * float(_saved_classic_comparison["Top1"].mean()), 2),
                            "Top 5%": round(100 * float(_saved_classic_comparison["Top5"].mean()), 2),
                            "Top 10%": round(100 * float(_saved_classic_comparison["Top10"].mean()), 2),
                            "Cash %": round(100 * float(_saved_classic_comparison["CashRate"].mean()), 2),
                        }])
                        st.write("### Field Sanity Check")
                        st.dataframe(injury_frame(st, _saved_classic_sanity), use_container_width=True, hide_index=True)

            classic_results = st.session_state.get("classic_lineups")
            if classic_results is not None:
                # Never display old lineups that contain a player now marked Out,
                # faded, or otherwise removed from the current eligible pool.
                current_eligible_names = set(classic_pool["Name"].astype(str))
                export_slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
                if all(slot in classic_results.columns for slot in export_slots):
                    valid_rows = classic_results[export_slots].apply(
                        lambda row: all(str(name) in current_eligible_names for name in row),
                        axis=1
                    )
                    if not valid_rows.all():
                        classic_results = classic_results.loc[valid_rows].reset_index(drop=True)
                        st.session_state["classic_lineups"] = classic_results
                        st.session_state.pop("classic_contest_field_df", None)
                        st.session_state.pop("classic_contest_comparison_df", None)
                        st.warning("Removed saved lineups containing players no longer eligible. Click BUILD to create replacement lineups.")
                if not classic_results.empty:
                    st.write(f"Built {len(classic_results)} valid Classic lineups.")
                classic_display = classic_results.drop(columns=["Score"], errors="ignore").copy()
                classic_sim = st.session_state.get("simulation_df")
                if isinstance(classic_sim, pd.DataFrame) and not classic_sim.empty:
                    classic_means = classic_sim.mean(axis=0, numeric_only=True).to_dict()
                    classic_floors = classic_sim.quantile(0.10, axis=0).to_dict()
                    classic_ceilings = classic_sim.quantile(0.90, axis=0).to_dict()
                    for slot in export_slots:
                        if slot in classic_display.columns:
                            classic_display[slot + " Sim Pts"] = classic_display[slot].map(
                                lambda name: round(float(classic_means.get(str(name), 0.0)), 2)
                            )
                            classic_display[slot + " Floor (P10)"] = classic_display[slot].map(
                                lambda name: round(float(classic_floors.get(str(name), 0.0)), 2)
                            )
                            classic_display[slot + " Ceiling (P90)"] = classic_display[slot].map(
                                lambda name: round(float(classic_ceilings.get(str(name), 0.0)), 2)
                            )
                    ordered_cols = []
                    for slot in export_slots:
                        if slot in classic_display.columns:
                            ordered_cols.extend([slot, slot + " Sim Pts", slot + " Floor (P10)", slot + " Ceiling (P90)"])
                    classic_display["Total Sim Pts"] = classic_display[
                        [slot + " Sim Pts" for slot in export_slots if slot + " Sim Pts" in classic_display.columns]
                    ].apply(pd.to_numeric, errors="coerce").sum(axis=1).round(2)
                    # Use combined lineup outcomes to calculate lineup-level floor and ceiling.
                    lineup_floor_values = []
                    lineup_ceiling_values = []
                    for _, lineup_row in classic_display.iterrows():
                        lineup_names = [str(lineup_row[slot]) for slot in export_slots if slot in classic_display.columns]
                        valid_names = [name for name in lineup_names if name in classic_sim.columns]
                        if valid_names:
                            lineup_outcomes = classic_sim[valid_names].sum(axis=1)
                            lineup_floor_values.append(round(float(lineup_outcomes.quantile(0.10)), 2))
                            lineup_ceiling_values.append(round(float(lineup_outcomes.quantile(0.90)), 2))
                        else:
                            lineup_floor_values.append(0.0)
                            lineup_ceiling_values.append(0.0)
                    classic_display["Total Floor (P10)"] = lineup_floor_values
                    classic_display["Total Ceiling (P90)"] = lineup_ceiling_values
                    ordered_cols.extend(["Total Sim Pts", "Total Floor (P10)", "Total Ceiling (P90)"])
                    ordered_cols.extend(c for c in classic_display.columns if c not in ordered_cols)
                    classic_display = classic_display[ordered_cols]
                st.dataframe(
                    injury_frame(st, classic_display),
                    use_container_width=True,
                    hide_index=True
                )

                # Classic portfolio controls match the larger portfolio selector used by other formats.
                st.divider()
                st.write("## Portfolio")
                st.caption("Browse up to 5,000 candidates. The assigned portfolio below fills your reserved contest entries and is the source for both downloads.")
                classic_portfolio_source = st.session_state.get("classic_contest_comparison_df") if st.session_state.get("classic_field_context") == classic_contest_name else None
                render_value_leverage_finder(control_display, classic_portfolio_source,
                    st.session_state.get("classic_contest_field_df"),
                    ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"], "dk_classic")
                if not isinstance(classic_portfolio_source, pd.DataFrame) or classic_portfolio_source.empty:
                    classic_portfolio_source = classic_results.copy()
                # Match the Showdown ranking menu across all formats.
                if not all(metric in classic_portfolio_source.columns for metric in PORTFOLIO_METRICS.values()):
                    classic_portfolio_source = add_field_ranking_metrics(
                        classic_portfolio_source,
                        classic_portfolio_source.get("ProjectedPoints", pd.Series(dtype=float)).to_numpy(dtype=float)
                    )
                classic_rank_options = list(PORTFOLIO_METRICS.keys())
                classic_portfolio_count = st.number_input(
                    "Number of lineups to show",
                    min_value=1,
                    max_value=min(5000, max(1, len(classic_portfolio_source))),
                    value=min(20, max(1, len(classic_portfolio_source))),
                    step=1,
                    key="dk_classic_portfolio_count"
                )
                classic_rank_label = st.selectbox(
                    "Rank lineups by",
                    classic_rank_options,
                    index=classic_rank_options.index("Top 1%"),
                    key="dk_classic_portfolio_metric_top1_default_v2"
                )
                classic_rank_metric = PORTFOLIO_METRICS[classic_rank_label]
                from simmah_portfolio_selection import select_portfolio, put_portfolio_first
                _classic_assignment_count = max(1, int((st.session_state.get("selected_dk_contest") or {}).get("your_entries") or classic_entry_count))
                _classic_slots = [col for col in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"] if col in classic_portfolio_source]
                try:
                    classic_export_portfolio = select_portfolio(classic_portfolio_source, _classic_slots,
                        _classic_assignment_count, classic_rank_metric, controls=control_map, diversity=portfolio_diversity)
                except ValueError as exc:
                    st.error(str(exc))
                    workspace_stop(st, _loaded_slate_tabs)
                if classic_export_portfolio.attrs.get("effective_auto_cap_pct", 100) > (100 - .4 * portfolio_diversity):
                    st.warning(f"The candidate pool cannot fill all assigned entries at the preferred exposure cap. Automatic cap increased to {classic_export_portfolio.attrs['effective_auto_cap_pct']}%; your manual exposure limits remain enforced.")
                with _tab_lineups:
                    classic_export_portfolio = render_editor(st, classic_export_portfolio, classic_pool, _classic_slots,
                        "DraftKings", "Classic", st.session_state.get("selected_dk_contest", {}),
                        validator=lambda row: full_roster_stack_matches(row, classic_pool, dk_classic_stack_rules, secondary_stacks=dk_secondary_stack_rules))
                _classic_unique_entries = classic_export_portfolio.copy()
                classic_top_portfolio = put_portfolio_first(classic_portfolio_source, classic_export_portfolio,
                    _classic_slots).head(int(classic_portfolio_count)).copy()
                st.caption(f"Lineup exposure diversity: {portfolio_diversity}%. Preferred player cap: {100 - .4 * portfolio_diversity:.0f}%. Manual limits remain enforced; display count does not change assigned entries.")
                st.session_state["classic_contest_entries_df"] = classic_export_portfolio.copy()
                classic_top_portfolio["Assigned to contest"] = np.arange(len(classic_top_portfolio)) < len(_classic_unique_entries)
                _classic_portfolio_field = st.session_state.get("classic_contest_field_df")
                _classic_portfolio_outcomes = st.session_state.get("simulation_df")
                if st.session_state.get("classic_field_context") == classic_contest_name and isinstance(_classic_portfolio_field, pd.DataFrame) and not _classic_portfolio_field.empty:
                    with st.expander("Opponent field diagnostics"):
                        st.caption("This estimated field determines finish rates and ROI. Construction learning does not validate future ownership or profitability.")
                        _diagnostic_rows = []
                        for _label, _frame in [("Opponent field", _classic_portfolio_field), ("Assigned portfolio", classic_export_portfolio)]:
                            _diagnostic_rows.append({"Group": _label, "Lineups": len(_frame),
                                "Mean salary": float(pd.to_numeric(_frame["Salary"], errors="coerce").mean()),
                                "Mean simulated points": float(pd.to_numeric(_frame["ProjectedPoints"], errors="coerce").mean())})
                        st.dataframe(injury_frame(st, pd.DataFrame(_diagnostic_rows)), hide_index=True, use_container_width=True)
                        st.download_button("DOWNLOAD CLASSIC OPPONENT FIELD", _classic_portfolio_field.to_csv(index=False).encode("utf-8"),
                            "DraftKings_Classic_Opponent_Field.csv", "text/csv", key="classic_field_diagnostics", on_click="ignore")
                        _ownership_snapshot = st.session_state.get("classic_ownership_snapshot")
                        if isinstance(_ownership_snapshot, pd.DataFrame) and not _ownership_snapshot.empty:
                            st.download_button("DOWNLOAD OWNERSHIP SNAPSHOT", _ownership_snapshot.to_csv(index=False).encode("utf-8"),
                                "DraftKings_Classic_Ownership_Snapshot.csv", "text/csv", key="classic_ownership_snapshot_download", on_click="ignore")
                        st.download_button("DOWNLOAD CLASSIC PLAYER INPUTS", classic_pool.to_csv(index=False).encode("utf-8"),
                            "DraftKings_Classic_Player_Inputs.csv", "text/csv", key="classic_player_diagnostics", on_click="ignore")

                if st.session_state.get("classic_field_context") == classic_contest_name and isinstance(_classic_portfolio_field, pd.DataFrame) and not _classic_portfolio_field.empty and isinstance(_classic_portfolio_outcomes, pd.DataFrame):
                    with st.spinner("Evaluating the selected portfolio together..."):
                        classic_export_portfolio = evaluate_full_roster_portfolio_cached(
                            _classic_portfolio_outcomes, classic_export_portfolio, _classic_portfolio_field,
                            [slot for slot,_ in roster_slots], int(classic_contest["field"]),
                            classic_contest["payouts"], float(classic_contest["entry"]))
                    st.session_state["classic_contest_entries_df"] = classic_export_portfolio
                    st.caption(f"{_classic_assignment_count} assigned contest entries are evaluated jointly, including repeated lineups when needed to fill the entry template. Additional displayed candidates are alternatives, not extra owned entries. The opponent field remains an estimate.")
                    st.write("### Assigned contest portfolio")
                    st.dataframe(injury_frame(st, classic_export_portfolio), use_container_width=True, hide_index=True)
                else:
                    st.caption("Run CONTEST SIM for field-based portfolio metrics.")
                render_portfolio_roi_panel(classic_export_portfolio, classic_contest)
                st.caption("Candidate alternatives — only rows marked Assigned to contest are included in your entry replacement.")
                st.dataframe(injury_frame(st, classic_top_portfolio), use_container_width=True, hide_index=True)

                lineup_export_download(
                    label="DOWNLOAD ASSIGNED PORTFOLIO REPORT",
                    data=classic_export_portfolio.to_csv(index=False).encode("utf-8"),
                    file_name="DraftKings_Classic_Assigned_Portfolio.csv",
                    mime="text/csv",
                    key="dk_classic_assigned_report",
                    on_click="ignore"
                )

                classic_results = remove_out_players_from_lineups(
                    classic_results, ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"], "DraftKings Classic"
                )
                st.session_state["classic_lineups"] = classic_results
                id_column = "DK_ID" if "DK_ID" in classic_pool.columns else None
                if id_column:
                    ids = dict(zip(classic_pool["Name"], classic_pool[id_column].astype(str)))
                    export_slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
                    export_data = []
                    missing = []
                    for _, lineup in classic_export_portfolio.iterrows():
                        row_ids = []
                        for slot in export_slots:
                            player_name = lineup[slot]
                            player_id = ids.get(player_name, "")
                            if not player_id or player_id.lower() == "nan":
                                missing.append(player_name)
                            row_ids.append(player_id)
                        export_data.append(row_ids)
                    if missing:
                        st.warning("Some player IDs are missing. Upload the DraftKings lineup template to enable export.")
                    else:
                        # Keep the official DraftKings entry upload separate from a basic lineup export.
                        dk_upload_columns = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
                        lineup_ids_df = pd.DataFrame(export_data, columns=dk_upload_columns)
                        render_entry_export_header("DraftKings")
                        has_entry_template = (
                            entry_file is not None
                            and selected_contest_id
                            and "entry_df" in locals()
                            and isinstance(entry_df, pd.DataFrame)
                            and not entry_df.empty
                        )
                        if has_entry_template:
                            st.caption("FOR EXISTING ENTRIES: Download this file, then go to DraftKings → My Lineups → Edit Entries → Upload CSV. Do not upload this file on the regular Upload Lineups page. Entry IDs and Contest ID are preserved.")
                            export_df = build_dk_contest_entry_export(
                                entry_df,
                                selected_contest_id,
                                lineup_ids_df,
                                dk_upload_columns,
                                "Classic"
                            )
                            if export_df is not None:
                                lineup_export_download(
                                    label="DOWNLOAD FILE FOR EDIT ENTRIES",
                                    data=export_df.to_csv(index=False).encode("utf-8"),
                                    file_name="DraftKings_Classic_Contest_Entries.csv",
                                    mime="text/csv",
                                    use_container_width=True,
                                    key="dk_classic_replace_export",
                                    on_click="ignore"
                                )
                                st.caption("On DraftKings, open My Lineups and choose Edit Entries to upload the downloaded replacement CSV.")
                        else:
                            st.warning(
                                "To put these lineups into your existing entries, upload the CSV from DraftKings "
                                "My Contests / Edit Entries in this app and select the matching contest. "
                                "Then this app will make one replacement file that preserves Entry IDs and Contest ID. "
                                "A separate new-lineups export is intentionally disabled."
                            )
                else:
                    st.info("Upload a DraftKings salary/template CSV containing player IDs to enable lineup export.")

            # Re-render the player table, which appears before the SIM button.
            if classic_run_all:
                workspace_rerun(st, _loaded_slate_tabs)
            workspace_stop(st, _loaded_slate_tabs)


# ============================================
# BUILD LINEUPS
# ============================================

# One-click workflow: SIM runs player simulations, builds the user's candidate lineups,
# builds the opponent field, then scores the contest.

with _tab_build:
    if platform == "DraftKings" and lineup_mode == "Showdown":
        render_saved_market_calibration(platform, lineup_mode, players_df)
    build_cols = [_build_controls.container() for _ in range(3)]
    with build_cols[0]:
        st.write("### Build Settings")
        _fd_full = platform == "FanDuel" and lineup_mode == "Full Roster"
        _salary_cap = 60000 if _fd_full else 50000
        _salary_default = (58000, 60000) if _fd_full else ((40000, 50000) if lineup_mode in ("Showdown", "Single Game") else (48000, 50000))
        dk_salary_range = st.slider(
            "Allowed lineup salary range",
            min_value=0,
            max_value=_salary_cap,
            value=_salary_default,
            step=100,
            format="$%d",
            key="dk_build_salary_range_" + platform.lower() + "_" + lineup_mode.replace(" ", "_").lower(),
            help="Only build lineups whose total salary falls inside this range."
        )
    MIN_LINEUP_SALARY, MAX_LINEUP_SALARY = dk_salary_range
    with build_cols[1]:
        portfolio_diversity, aggressiveness = render_diversity_controls(st, platform, lineup_mode, SIMULATION_COUNT)
        if lineup_mode in ("Showdown", "Single Game"):
            correlation_pct = st.slider(
                "Game Correlation", 0, 100,
                0 if ((platform == "DraftKings" and lineup_mode == "Showdown") or (platform == "FanDuel" and lineup_mode == "Single Game")) else 70,
                step=5,
                help="Controls how strongly shared game conditions connect player outcomes.",
                key=f"single_game_correlation_strength_{platform}_{lineup_mode}",
            )
            correlation_strength = correlation_pct / 100.0
        else:
            correlation_strength = 1.0
        st.session_state["active_game_correlation_strength"] = correlation_strength
    with build_cols[2]:
        st.write("### Run")
        build_clicked = st.button(
            "Run Build",
            type="primary",
            use_container_width=True
        )

    # ============================================
    # BUILD ACTION
    # ============================================

    # Prepare the eligible player pool BEFORE the button handler runs. The
    # Showdown SIM handler uses these lists immediately after player simulation.
    available_players = [
        p for p in players_df["Name"]
        if p in control_map and not control_map[p].get("Fade", False)
    ]
    locked_players = [
        p for p in available_players
        if control_map[p].get("Lock", False)
    ]

    if build_clicked:
        # Keep a persistent status message and surface failures instead of letting
        # the player progress bar vanish without telling the user what failed.
        workflow_status = st.empty()
        workflow_status.info(f"Step 1 of 4: Running {SIMULATION_COUNT:,} player simulations...")
        try:
            simulation_df = run_game_simulations(
                players_df, platform=platform, workflow_status=workflow_status
            )
            if not isinstance(simulation_df, pd.DataFrame) or simulation_df.empty:
                raise RuntimeError("The player simulation returned no results.")
            st.session_state["simulation_df"] = simulation_df
            st.session_state["simulations_ready"] = True

            workflow_status.info("Step 2 of 4: Preparing rankings and building your candidate lineups...")

            # Refresh rankings with the simulations created by this SIM click.
            player_sim = {}
            missing_simulation_columns = [
                str(player) for player in players_df["Name"]
                if player not in simulation_df.columns
            ]
            if missing_simulation_columns:
                raise RuntimeError(
                    "Simulation results are missing player columns: "
                    + ", ".join(missing_simulation_columns[:10])
                )
            for player in players_df["Name"]:
                values = pd.to_numeric(simulation_df[player], errors="coerce").dropna()
                if values.empty:
                    raise RuntimeError(f"No usable simulated scores were returned for {player}.")
                player_sim[player] = {
                    "Mean": float(values.mean()),
                    "P95": float(values.quantile(0.95)),
                    "P99": float(values.quantile(0.99)),
                    "StdDev": float(values.std(ddof=0))
                }
        except Exception as exc:
            workflow_status.error(
                f"SIM stopped during player simulations or ranking setup: {type(exc).__name__}: {exc}"
            )
            st.exception(exc)
            workspace_stop(st, _loaded_slate_tabs)

    # The eligible player pool was prepared before the SIM handler above.
    # Keep the last successful candidate pool across Streamlit reruns.
    candidates_df = st.session_state.get("candidates_df")

    # ============================================
    # RANK PLAYERS
    # ============================================

    if build_clicked:
        workflow_status.info("Step 2 of 4: Preparing rankings and building your candidate lineups...")
        try:
            showdown_pool = players_df[players_df["Name"].isin(available_players)].drop_duplicates("Name").reset_index(drop=True)
            showdown_roster = [("Captain", set())] + [(f"Flex{i}", set()) for i in range(1, 6)]
            allowed_captains = {name for name in showdown_pool["Name"] if control_map.get(name, {}).get("Captain Max %", 100)>0}
            costs = np.vstack([
                showdown_pool["Name"].map(captain_salary_map).to_numpy(float),
                *[showdown_pool["Name"].map(salary_map).to_numpy(float) for _ in range(5)],
            ])
            candidates_df = build_joint_candidate_pool(showdown_pool, "DraftKings", "Showdown", simulation_df,
                showdown_roster, MIN_LINEUP_SALARY, min(SALARY_CAP, MAX_LINEUP_SALARY),
                locks=locked_players, special_allowed=allowed_captains, salary_costs=costs, aggressiveness=aggressiveness)
        except Exception as exc:
            workflow_status.error(
                f"Step 2 failed while ranking players or building candidate lineups: {type(exc).__name__}: {exc}"
            )
            st.exception(exc)
            workspace_stop(st, _loaded_slate_tabs)


        st.session_state["candidates_df"] = candidates_df
        st.session_state["candidates_ready"] = True

    if isinstance(candidates_df, pd.DataFrame):
        st.write(f"Candidate lineups tested: {len(candidates_df):,}")

    if build_clicked:
        # Step 3: build the simulated opponent field after our candidate lineups exist.

        workflow_status.info(f"Step 3 of 4: Building up to {dk_opponent_target:,} simulated opponent lineups...")
        field_progress = st.progress(0, text=f"Step 3 of 4: Building opponent lineups (0 of {dk_opponent_target:,})...")
        try:
            # First generate the representative 10,000-lineup sample, then use
            # ownership observed in that sample to estimate a full contest field.
            contest_field_sample_df = build_showdown_opponent_field(
                available_players, simulation_df, players_df, salary_map,
                captain_salary_map, SALARY_CAP, dk_opponent_target,
                progress_bar=field_progress
            )
        except Exception as exc:
            workflow_status.error(f"Step 3 failed while building opponent lineups: {type(exc).__name__}: {exc}")
            st.exception(exc)
            workspace_stop(st, _loaded_slate_tabs)
        field_progress.progress(1.0, text=f"Step 3 of 4 complete: {len(contest_field_sample_df):,} unique sample opponent lineups created")
        if len(contest_field_sample_df) < dk_opponent_target:
            st.warning(f"Only {len(contest_field_sample_df):,} distinct legal opponents are available under the current pool and salary limits; requested {dk_opponent_target:,}. No duplicate sample rows were added.")
        if contest_field_sample_df.empty:
            workflow_status.error(
                "Step 3 could not create any valid opponent lineups. Check the salary cap and eligible player pool."
            )
            workspace_stop(st, _loaded_slate_tabs)

        selected_contest = st.session_state.get("selected_dk_contest") or {}
        try:
            full_field_size = int(selected_contest.get("field_size") or (dk_opponent_target + 1))
        except (TypeError, ValueError):
            full_field_size = dk_opponent_target + 1
        try:
            own_entries = max(0, int(selected_contest.get("your_entries", 0) or 0))
        except (TypeError, ValueError):
            own_entries = 0
        full_opponent_count = max(1, full_field_size - own_entries)
        contest_field_df = expand_showdown_field_by_ownership(
            contest_field_sample_df, full_opponent_count
        )

        st.session_state["contest_field_sample_df"] = contest_field_sample_df
        st.session_state["contest_field_df"] = contest_field_df
        st.session_state["contest_field_count"] = len(contest_field_df)
        st.session_state["contest_field_ready"] = len(contest_field_df) > 0

        if selected_contest:
            st.info(
                f"Contest selected from your entry CSV: {selected_contest.get('name', 'DraftKings contest')} "
                f"(ID {selected_contest.get('id', 'unknown')}). Your uploaded file has "
                f"{own_entries} of your entries in this contest. Built {len(contest_field_sample_df):,} "
                f"unique representative lineups, then expanded them without a second ownership weighting to "
                f"{len(contest_field_df):,} estimated opponent entries, allowing exact lineup duplicates. "
                "This is an estimate; the entry CSV does not contain the actual opponent lineups."
            )
        else:
            st.info(
                f"Built {len(contest_field_sample_df):,} representative lineups and expanded them to "
                f"{len(contest_field_df):,} estimated opponent entries, expanded without reweighting ownership."
            )



    # Step 4 belongs directly below the completed Step 3 field-building section.
    # Keep this unconditional so saved builds can be rescored safely on reruns.
    contest_progress_slot = st.empty()

    # Simulated field ownership is displayed in the Player Pool table, so do not render a duplicate table here.

    with _contest_setup:
        with st.expander("Contest Payout Structure", expanded=False):
            st.caption(
                "Fetch contest details from DraftKings first. If the public endpoint does not expose every payout tier, "
                "upload the payout table CSV shown in the contest details. Opponent lineups remain simulated."
            )

            _selected_dk_for_details = st.session_state.get("selected_dk_contest", {})
            if _selected_dk_for_details.get("id"):
                st.caption(
                    f"Selected contest: {_selected_dk_for_details.get('name', 'DraftKings contest')} "
                    f"(ID {_selected_dk_for_details['id']})"
                )
                _fetch_dk_details_clicked = st.button(
                    "FETCH DRAFTKINGS CONTEST DETAILS",
                    key="fetch_dk_contest_details",
                    use_container_width=True,
                )
                _selected_contest_id_for_payout = str(_selected_dk_for_details.get("id", "")).strip()
                _payout_needs_refresh = (
                    bool(_selected_contest_id_for_payout)
                    and (
                        str(st.session_state.get("contest_payout_contest_id", "")) != _selected_contest_id_for_payout
                        or not isinstance(st.session_state.get("contest_payout_schedule"), np.ndarray)
                        or len(st.session_state.get("contest_payout_schedule", [])) == 0
                    )
                )
                if _fetch_dk_details_clicked or _payout_needs_refresh:
                    try:
                        _contest_id_for_api = str(_selected_dk_for_details["id"]).strip()
                        if not _contest_id_for_api.isdigit():
                            raise ValueError("Contest ID must contain digits only.")
                        _dk_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
                            "Accept": "application/json, text/plain, */*",
                            "Referer": "https://www.draftkings.com/",
                        }
                        _dk_payload = None
                        _dk_source = ""
                        _dk_api_error = None

                        # Try the detailed endpoint first. Some deployments return HTTP 403,
                        # so fall back to the public lobby feed rather than stopping immediately.
                        try:
                            _dk_response = requests.get(
                                f"https://api.draftkings.com/contests/v1/contests/{_contest_id_for_api}?format=json",
                                headers=_dk_headers,
                                timeout=8,
                            )
                            _dk_response.raise_for_status()
                            _dk_payload = _dk_response.json()
                            _dk_source = "contest details endpoint"
                        except Exception as _api_exc:
                            _dk_api_error = f"{type(_api_exc).__name__}: {_api_exc}"

                        if _dk_payload is None:
                            _dk_lobby_response = requests.get(
                                "https://www.draftkings.com/lobby/getcontests?sport=NFL",
                                headers=_dk_headers,
                                timeout=12,
                            )
                            _dk_lobby_response.raise_for_status()
                            _dk_lobby_payload = _dk_lobby_response.json()

                            # Lobby payload shapes vary. Search nested objects for the exact
                            # contest ID and use only that contest's own details.
                            _dk_matches = []
                            def _find_dk_contest(obj):
                                if isinstance(obj, dict):
                                    _normalized = {str(k).casefold(): v for k, v in obj.items()}
                                    _id_value = next(
                                        (_normalized[k] for k in ("contestid", "contest_id", "id") if k in _normalized),
                                        None,
                                    )
                                    if _id_value is not None and str(_id_value).strip() == _contest_id_for_api:
                                        _dk_matches.append(obj)
                                    for _child in obj.values():
                                        _find_dk_contest(_child)
                                elif isinstance(obj, list):
                                    for _child in obj:
                                        _find_dk_contest(_child)
                            _find_dk_contest(_dk_lobby_payload)
                            if not _dk_matches:
                                raise ValueError(
                                    "The detailed endpoint was blocked and the public NFL lobby feed did not contain "
                                    f"contest ID {_contest_id_for_api}. Details endpoint error: {_dk_api_error}"
                                )
                            _dk_payload = _dk_matches[0]
                            _dk_source = "public NFL lobby feed (fallback)"

                        _dk_details = _dk_payload.get("contestDetail", _dk_payload) if isinstance(_dk_payload, dict) else None
                        if not isinstance(_dk_details, dict):
                            raise ValueError("DraftKings returned an unexpected contest-details format.")

                        _dk_summary = {
                            "contest_id": _contest_id_for_api,
                            "fetched_at": _sticky_datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p ET"),
                            "source": _dk_source,
                            "name": _dk_details.get("contestName") or _dk_details.get("name") or _selected_dk_for_details.get("name"),
                            "entry_fee": _dk_details.get("entryFee") or _dk_details.get("entry_fee") or _selected_dk_for_details.get("entry_fee"),
                            "entries": _dk_details.get("entries") or _dk_details.get("currentEntries") or _dk_details.get("current_entries"),
                            "maximum_entries": _dk_details.get("maximumEntries") or _dk_details.get("maxEntries") or _dk_details.get("maximum_entries"),
                            "prize_pool": _dk_details.get("prizePool") or _dk_details.get("totalPrizes") or _dk_details.get("prize_pool"),
                            "contest_summary": _dk_details.get("contestSummary") or _dk_details.get("contest_summary") or "",
                            "payout_description": _dk_details.get("payoutDescription") or _dk_details.get("payout_description") or "",
                        }
                        st.session_state["dk_contest_details"] = _dk_summary

                        # Find a complete payout ladder automatically. DraftKings sometimes puts
                        # tiers in structured JSON, sometimes in embedded page text. Never accept
                        # a partial ladder: ranks must be contiguous from 1 through the last paid
                        # position, and when a prize-pool total is available the dollars must match.
                        _payout_rows = []
                        _rank_keys = ("rank", "place", "position", "finish", "minRank", "min_rank", "startRank")
                        _prize_keys = ("prize", "payout", "winnings", "amount", "prizeAmount", "payoutAmount")

                        def _add_payout_range(start_rank, end_rank, prize):
                            try:
                                start_rank = int(start_rank)
                                end_rank = int(end_rank)
                                prize = float(prize)
                            except (TypeError, ValueError):
                                return
                            if start_rank < 1 or end_rank < start_rank or end_rank > 100000 or prize <= 0:
                                return
                            for rank in range(start_rank, end_rank + 1):
                                _payout_rows.append((rank, prize))

                        def _walk_dk_payout_objects(obj):
                            if isinstance(obj, dict):
                                normalized = {str(k).casefold(): v for k, v in obj.items()}
                                rank_value = next((normalized[k.casefold()] for k in _rank_keys if k.casefold() in normalized), None)
                                prize_value = next((normalized[k.casefold()] for k in _prize_keys if k.casefold() in normalized), None)
                                if rank_value is not None and prize_value is not None:
                                    try:
                                        rank_num = int(float(str(rank_value).replace(",", "")))
                                        prize_num = float(str(prize_value).replace("$", "").replace(",", ""))
                                        end_value = next((normalized[k.casefold()] for k in ("maxRank", "max_rank", "endRank", "toRank") if k.casefold() in normalized), rank_num)
                                        end_num = int(float(str(end_value).replace(",", "")))
                                        _add_payout_range(rank_num, end_num, prize_num)
                                    except (TypeError, ValueError):
                                        pass
                                for child in obj.values():
                                    _walk_dk_payout_objects(child)
                            elif isinstance(obj, list):
                                for child in obj:
                                    _walk_dk_payout_objects(child)

                        def _parse_payout_text(value):
                            import html as _html
                            raw = _html.unescape(str(value or ""))
                            if "$" not in raw:
                                return
                            cleaned = re.sub(r"<[^>]+>", " ", raw)
                            cleaned = re.sub(r"\s+", " ", cleaned)
                            occupied = []
                            range_pattern = re.compile(
                                r"(?<!\d)(\d{1,6})(?:st|nd|rd|th)?\s*(?:-|–|—|to)\s*"
                                r"(\d{1,6})(?:st|nd|rd|th)?[^$]{0,40}\$\s*"
                                r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
                                flags=re.IGNORECASE,
                            )
                            for match in range_pattern.finditer(cleaned):
                                _add_payout_range(
                                    match.group(1), match.group(2), match.group(3).replace(",", "")
                                )
                                occupied.append(match.span())

                            single_pattern = re.compile(
                                r"(?<!\d)(\d{1,6})(?:st|nd|rd|th)?"
                                r"(?:\s*(?:place|position))?[^$\d]{0,35}\$\s*"
                                r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
                                flags=re.IGNORECASE,
                            )
                            for match in single_pattern.finditer(cleaned):
                                if any(start <= match.start() < end for start, end in occupied):
                                    continue
                                _add_payout_range(
                                    match.group(1), match.group(1), match.group(2).replace(",", "")
                                )

                        def _walk_dk_payout_text(obj):
                            if isinstance(obj, dict):
                                for child in obj.values():
                                    _walk_dk_payout_text(child)
                            elif isinstance(obj, list):
                                for child in obj:
                                    _walk_dk_payout_text(child)
                            elif isinstance(obj, str) and "$" in obj:
                                _parse_payout_text(obj)

                        def _validated_payout_schedule(rows):
                            if not rows:
                                return None, None
                            payout_df = (
                                pd.DataFrame(rows, columns=["Rank", "Prize"])
                                .drop_duplicates("Rank", keep="last")
                                .sort_values("Rank")
                            )
                            if payout_df.empty:
                                return None, None
                            max_rank = int(payout_df["Rank"].max())
                            actual_ranks = set(payout_df["Rank"].astype(int).tolist())
                            if actual_ranks != set(range(1, max_rank + 1)):
                                return None, None
                            schedule = np.zeros(max_rank, dtype=float)
                            schedule[payout_df["Rank"].to_numpy(dtype=int) - 1] = payout_df["Prize"].to_numpy(dtype=float)
                            if np.any(schedule <= 0):
                                return None, None
                            expected_pool = pd.to_numeric(_dk_summary.get("prize_pool"), errors="coerce")
                            if pd.notna(expected_pool) and float(expected_pool) > 0:
                                tolerance = max(1.0, float(expected_pool) * 0.02)
                                if abs(float(schedule.sum()) - float(expected_pool)) > tolerance:
                                    return None, None
                            return payout_df, schedule

                        _walk_dk_payout_objects(_dk_payload)
                        _walk_dk_payout_text(_dk_payload)
                        _payout_df, _payout_schedule_auto = _validated_payout_schedule(_payout_rows)
                        _payout_source = "DraftKings contest details API"

                        # If the JSON does not expose a complete ladder, try the two public
                        # contest-detail pages. They sometimes contain the prize table in the
                        # rendered/embedded response even when the JSON endpoint only gives a summary.
                        if _payout_schedule_auto is None:
                            for _payout_page_url in (
                                f"https://www.draftkings.com/draft/contest/{_contest_id_for_api}",
                                f"https://www.draftkings.com/contest/gamecenter/{_contest_id_for_api}",
                            ):
                                try:
                                    _page_response = requests.get(
                                        _payout_page_url,
                                        headers=_dk_headers,
                                        timeout=10,
                                    )
                                    _page_response.raise_for_status()
                                    _page_rows_before = len(_payout_rows)
                                    _parse_payout_text(_page_response.text)
                                    if len(_payout_rows) > _page_rows_before:
                                        _payout_df, _payout_schedule_auto = _validated_payout_schedule(_payout_rows)
                                        if _payout_schedule_auto is not None:
                                            _payout_source = "DraftKings public contest page"
                                            break
                                except Exception:
                                    continue

                        if _payout_schedule_auto is not None:
                            st.session_state["contest_payout_schedule"] = _payout_schedule_auto
                            st.session_state["contest_payout_source_name"] = _payout_source
                            st.session_state["contest_payout_contest_id"] = _contest_id_for_api
                            st.session_state["contest_payout_auto_loaded"] = True
                            st.success(
                                f"DraftKings payout scale loaded automatically: "
                                f"{len(_payout_schedule_auto):,} paid finishing positions."
                            )
                        else:
                            st.session_state["contest_payout_auto_loaded"] = False
                            st.info(
                                "DraftKings contest details loaded, but a complete payout ladder was not publicly exposed. "
                                "The app will not guess missing ranks; upload the payout table only for contests where DraftKings blocks it."
                            )
                        # Continue into contest scoring on the same run. Restarting the
                        # Streamlit script here can trap the app in a fetch/rerun loop when
                        # DraftKings returns contest details without a complete payout table.
                    except Exception as exc:
                        st.warning(
                            f"Could not automatically load DraftKings contest details ({type(exc).__name__}: {exc}). "
                            "The endpoint may be unavailable or its format may have changed; you can still upload the payout CSV."
                        )

            _dk_details_display = st.session_state.get("dk_contest_details")
            _current_details_contest_id = str(st.session_state.get("selected_dk_contest", {}).get("id", ""))
            if isinstance(_dk_details_display, dict) and str(_dk_details_display.get("contest_id", "")) == _current_details_contest_id:
                _detail_cols = st.columns(4)
                _entry_fee_display = pd.to_numeric(_dk_details_display.get("entry_fee"), errors="coerce")
                _prize_pool_display = pd.to_numeric(_dk_details_display.get("prize_pool"), errors="coerce")
                _entries_display = pd.to_numeric(_dk_details_display.get("entries"), errors="coerce")
                _max_entries_display = pd.to_numeric(_dk_details_display.get("maximum_entries"), errors="coerce")
                _detail_cols[0].metric("Entry Fee", f"${_entry_fee_display:,.2f}" if pd.notna(_entry_fee_display) else "Not provided")
                _detail_cols[1].metric("Prize Pool", f"${_prize_pool_display:,.2f}" if pd.notna(_prize_pool_display) else "Not provided")
                _detail_cols[2].metric("Current Entries", f"{int(_entries_display):,}" if pd.notna(_entries_display) else "Not provided")
                _detail_cols[3].metric("Max Entries", f"{int(_max_entries_display):,}" if pd.notna(_max_entries_display) else "Not provided")
                if _dk_details_display.get("contest_summary"):
                    st.write(_dk_details_display["contest_summary"])
                if _dk_details_display.get("payout_description"):
                    st.write("**DraftKings payout description:** " + str(_dk_details_display["payout_description"]))
                st.caption("Source: " + str(_dk_details_display.get("source", "DraftKings endpoint")))
                st.caption("Last fetched: " + str(_dk_details_display.get("fetched_at", "unknown time")))

            payout_file = workspace_file_uploader(st,
                "Upload contest payout table CSV",
                type=["csv"],
                key="contest_payout_table_upload",
                help="Use the payout schedule shown in the DraftKings contest details. Include each paid rank."
            )
            if payout_file is not None:
                try:
                    payout_source = pd.read_csv(payout_file)
                    payout_lookup = {str(c).strip().casefold(): c for c in payout_source.columns}
                    rank_col = next((payout_lookup[k] for k in ("rank", "place", "position", "finish") if k in payout_lookup), None)
                    prize_col = next((payout_lookup[k] for k in ("prize", "payout", "winnings", "amount") if k in payout_lookup), None)
                    if rank_col is None or prize_col is None:
                        st.error("Payout CSV needs a Rank/Place column and a Prize/Payout column.")
                    else:
                        payout_source["_rank"] = pd.to_numeric(
                            payout_source[rank_col].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
                        )
                        payout_source["_prize"] = pd.to_numeric(
                            payout_source[prize_col].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce"
                        )
                        payout_source = payout_source.dropna(subset=["_rank", "_prize"])
                        payout_source = payout_source[payout_source["_rank"] >= 1].copy()
                        payout_source["_rank"] = payout_source["_rank"].astype(int)
                        payout_source = payout_source.sort_values("_rank").drop_duplicates("_rank", keep="last")
                        if payout_source.empty:
                            st.error("No valid rank/prize rows were found in the payout CSV.")
                        else:
                            payout_schedule = np.zeros(int(payout_source["_rank"].max()), dtype=float)
                            payout_schedule[payout_source["_rank"].to_numpy() - 1] = payout_source["_prize"].to_numpy(dtype=float)
                            st.session_state["contest_payout_schedule"] = payout_schedule
                            st.session_state["contest_payout_source_name"] = getattr(payout_file, "name", "uploaded payout CSV")
                            st.session_state["contest_payout_contest_id"] = str(
                                st.session_state.get("selected_dk_contest", {}).get("id", "")
                            )
                except Exception as exc:
                    st.error(f"Could not read payout table: {type(exc).__name__}: {exc}")

            # User-verified DAL @ GB $3K Dime Package payouts, scoped to the entry CSV's contest ID.
            if (
                str(st.session_state.get("selected_dk_contest", {}).get("id", "")) == "196786594"
                and str(st.session_state.get("contest_payout_contest_id", "")) != "196786594"
            ):
                _dal_gb_dime_ranges = [[1,1,150],[2,2,100],[3,3,60],[4,4,45],[5,5,35],[6,6,25],[7,8,20],[9,10,15],[11,13,10],[14,16,8],[17,20,6],[21,25,5],[26,35,4],[36,45,3],[46,60,2],[61,80,1.5],[81,135,1],[136,275,0.75],[276,625,0.5],[626,1420,0.4],[1421,3460,0.3],[3461,8545,0.2]]
                _dal_gb_dime_schedule = np.zeros(8545, dtype=float)
                for _rank_start, _rank_end, _rank_prize in _dal_gb_dime_ranges:
                    _dal_gb_dime_schedule[_rank_start - 1:_rank_end] = _rank_prize
                st.session_state["contest_payout_schedule"] = _dal_gb_dime_schedule
                st.session_state["contest_payout_source_name"] = "User-verified DAL @ GB $3K Dime Package payout table"
                st.session_state["contest_payout_contest_id"] = "196786594"
                st.session_state["contest_payout_auto_loaded"] = True


            # User-verified HOU vs JAX $300 Dime Package; never reuse for another contest.
            if (
                str(st.session_state.get("selected_dk_contest", {}).get("id", "")) == "196867391"
                and str(st.session_state.get("contest_payout_contest_id", "")) != "196867391"
            ):
                _hou_jax_dime_ranges = [[1,1,30],[2,2,15],[3,3,10],[4,4,5],[5,5,4],[6,7,3],[8,10,2],[11,15,1.5],[16,20,1],[21,30,0.75],[31,60,0.5],[61,130,0.4],[131,340,0.3],[341,830,0.2]]
                _hou_jax_dime_schedule = np.zeros(830, dtype=float)
                for _rank_start, _rank_end, _rank_prize in _hou_jax_dime_ranges:
                    _hou_jax_dime_schedule[_rank_start - 1:_rank_end] = _rank_prize
                st.session_state["contest_payout_schedule"] = _hou_jax_dime_schedule
                st.session_state["contest_payout_source_name"] = "User-verified HOU vs JAX $300 Dime Package payout table"
                st.session_state["contest_payout_contest_id"] = "196867391"
                st.session_state["contest_payout_auto_loaded"] = True


            # Verified payout schedule supplied from the DraftKings contest details.
            # Keep it scoped to this exact contest ID; never apply it to another contest.
            if (
                str(st.session_state.get("selected_dk_contest", {}).get("id", "")) == "196537800"
                and str(st.session_state.get("contest_payout_contest_id", "")) != "196537800"
            ):
                _known_dk_payout_ranges = [
                    (1, 1, 250.00), (2, 2, 150.00), (3, 3, 100.00), (4, 4, 75.00),
                    (5, 5, 50.00), (6, 6, 40.00), (7, 8, 30.00), (9, 10, 25.00),
                    (11, 13, 20.00), (14, 16, 15.00), (17, 20, 10.00), (21, 25, 8.00),
                    (26, 35, 6.00), (36, 45, 5.00), (46, 60, 4.00), (61, 75, 3.00),
                    (76, 100, 2.00), (101, 135, 1.50), (136, 215, 1.00),
                    (216, 425, 0.75), (426, 945, 0.50), (946, 2165, 0.40),
                    (2166, 5385, 0.30), (5386, 14240, 0.20),
                ]
                _known_dk_payout_schedule = np.zeros(14240, dtype=float)
                for _rank_start, _rank_end, _rank_prize in _known_dk_payout_ranges:
                    _known_dk_payout_schedule[_rank_start - 1:_rank_end] = _rank_prize
                st.session_state["contest_payout_schedule"] = _known_dk_payout_schedule
                st.session_state["contest_payout_source_name"] = "User-provided DraftKings payout table"
                st.session_state["contest_payout_contest_id"] = "196537800"

            # Verified payout ladder supplied from the DraftKings contest details for
            # NFL Showdown $4K Dime Package [Just $0.10!] (SEA @ DEN).
            # Match the exact contest name so this fallback cannot leak into another contest.
            # Saved DraftKings payout library fallback. Live DraftKings payout data keeps priority;
            # this only fills the payout schedule when the selected contest has no valid live scale.
            # Saved Showdown profiles are reusable templates across matchups.
            def _try_saved_dk_payout_library():
                _selected = st.session_state.get("selected_dk_contest", {}) or {}
                _selected_id = str(_selected.get("id", "")).strip()
                _selected_name = str(_selected.get("name", "")).strip()
                if not _selected_name:
                    return False
                _existing = st.session_state.get("contest_payout_schedule")
                _existing_id = str(st.session_state.get("contest_payout_contest_id", "")).strip()
                if _selected_id and _existing_id == _selected_id and isinstance(_existing, np.ndarray) and len(_existing):
                    return False
                try:
                    import json as _json
                    import re as _re
                    _library_path = Path(__file__).resolve().parent / "data" / "dk_payout_library.json"
                    if not _library_path.exists():
                        _library_path = Path("data/dk_payout_library.json")
                    if not _library_path.exists():
                        return False
                    _library = _json.loads(_library_path.read_text(encoding="utf-8"))
                except Exception:
                    return False

                def _contest_family(_name):
                    # DraftKings appends the game matchup in the final parenthetical. Remove only
                    # a team-vs-team suffix so contest labels such as [20 Entry Max] stay intact.
                    return _re.sub(r"\s*\([A-Z]{2,4}\s*@\s*[A-Z]{2,4}\)\s*$", "", str(_name or "")).strip()

                _selected_family = _contest_family(_selected_name)
                try:
                    _selected_fee = float(_selected.get("entry_fee")) if _selected.get("entry_fee") is not None else None
                except (TypeError, ValueError):
                    _selected_fee = None
                try:
                    _selected_field = int(_selected.get("field_size")) if _selected.get("field_size") else None
                except (TypeError, ValueError):
                    _selected_field = None
                try:
                    _selected_prize_pool = float(_selected.get("prize_pool")) if _selected.get("prize_pool") is not None else None
                except (TypeError, ValueError):
                    _selected_prize_pool = None

                for _profile in _library.get("profiles", []):
                    _profile_family = str(_profile.get("contest_family") or _contest_family(_profile.get("contest_name", ""))).strip()
                    if _profile_family != _selected_family:
                        continue
                    _profile_fee = _profile.get("entry_fee")
                    if _selected_fee is not None and _profile_fee is not None and abs(float(_profile_fee) - _selected_fee) > 0.001:
                        continue
                    _profile_pool = _profile.get("prize_pool")
                    if _selected_prize_pool is not None and _profile_pool is not None and abs(float(_profile_pool) - _selected_prize_pool) > 1.0:
                        continue
                    _profile_field = _profile.get("max_entries")
                    if _selected_field and _profile_field:
                        _tolerance = max(100, int(round(float(_profile_field) * 0.01)))
                        if abs(int(_profile_field) - int(_selected_field)) > _tolerance:
                            continue
                    _ranges = _profile.get("payout_ranges") or []
                    if not _ranges:
                        continue
                    try:
                        _paid_positions = max(int(r[1]) for r in _ranges)
                        _schedule = np.zeros(_paid_positions, dtype=float)
                        for _start, _end, _amount in _ranges:
                            _schedule[int(_start) - 1:int(_end)] = float(_amount)
                        _expected_total = _profile.get("verified_total_payout")
                        if _expected_total is not None and abs(float(_schedule.sum()) - float(_expected_total)) > 1.0:
                            continue
                    except Exception:
                        continue
                    st.session_state["contest_payout_schedule"] = _schedule
                    st.session_state["contest_payout_source_name"] = (
                        "Saved DraftKings payout library: " + str(_profile.get("contest_family") or _selected_family)
                    )
                    st.session_state["contest_payout_contest_id"] = _selected_id
                    st.session_state["contest_payout_auto_loaded"] = True
                    return True
                return False

            # User-provided WAS @ SF payout table, scoped to this exact contest.
            if str(st.session_state.get("selected_dk_contest", {}).get("id", "")) == "196786696":
                _was_sf_ranges = [(1, 1, 250), (2, 2, 150), (3, 3, 100), (4, 4, 75), (5, 5, 50), (6, 6, 40), (7, 8, 30), (9, 10, 25), (11, 13, 20), (14, 16, 15), (17, 20, 10), (21, 25, 8), (26, 35, 6), (36, 45, 5), (46, 60, 4), (61, 75, 3), (76, 100, 2), (101, 135, 1.5), (136, 215, 1), (216, 425, 0.75), (426, 945, 0.5), (946, 2165, 0.4), (2166, 5385, 0.3), (5386, 14240, 0.2)]
                _was_sf_schedule = np.zeros(14240, dtype=float)
                for _first, _last, _prize in _was_sf_ranges:
                    _was_sf_schedule[_first - 1:_last] = _prize
                st.session_state["contest_payout_schedule"] = _was_sf_schedule
                st.session_state["contest_payout_contest_id"] = "196786696"
                st.session_state["contest_payout_source_name"] = "User-verified WAS @ SF $5K payout table"
                st.session_state["contest_payout_auto_loaded"] = True

            _try_saved_dk_payout_library()

            _selected_dk_name = str(st.session_state.get("selected_dk_contest", {}).get("name", "")).strip()
            _selected_dk_id = str(st.session_state.get("selected_dk_contest", {}).get("id", "")).strip()
            if (
                _selected_dk_name == "NFL Showdown $4K Dime Package [Just $0.10!] (SEA @ DEN)"
                and str(st.session_state.get("contest_payout_contest_id", "")) != _selected_dk_id
            ):
                _sea_den_dime_ranges = [
                    (1, 1, 200.00), (2, 2, 150.00), (3, 3, 100.00), (4, 4, 75.00),
                    (5, 5, 60.00), (6, 6, 50.00), (7, 7, 40.00), (8, 8, 30.00),
                    (9, 9, 25.00), (10, 10, 20.00), (11, 15, 15.00), (16, 20, 10.00),
                    (21, 25, 8.00), (26, 30, 6.00), (31, 40, 5.00), (41, 50, 4.00),
                    (51, 65, 3.00), (66, 85, 2.00), (86, 110, 1.50), (111, 155, 1.00),
                    (156, 275, 0.75), (276, 585, 0.50), (586, 1385, 0.40),
                    (1386, 3670, 0.30), (3671, 11405, 0.20),
                ]
                _sea_den_dime_schedule = np.zeros(11405, dtype=float)
                for _rank_start, _rank_end, _rank_prize in _sea_den_dime_ranges:
                    _sea_den_dime_schedule[_rank_start - 1:_rank_end] = _rank_prize
                # The supplied payout ladder totals exactly $4,000.
                st.session_state["contest_payout_schedule"] = _sea_den_dime_schedule
                st.session_state["contest_payout_source_name"] = "Verified SEA @ DEN $4K Dime Package payout table"
                st.session_state["contest_payout_contest_id"] = _selected_dk_id
                st.session_state["contest_payout_auto_loaded"] = True

            # Verified payout ladder supplied from the DraftKings contest details for
            # NFL Showdown $4K Dime Package [Just $0.10!] (SEA @ DEN).
            # Match the exact contest name so this fallback cannot leak into another contest.
            _selected_dk_name = str(st.session_state.get("selected_dk_contest", {}).get("name", "")).strip()
            _selected_dk_id = str(st.session_state.get("selected_dk_contest", {}).get("id", "")).strip()
            if (
                _selected_dk_name == "NFL Showdown $4K Dime Package [Just $0.10!] (SEA @ DEN)"
                and str(st.session_state.get("contest_payout_contest_id", "")) != _selected_dk_id
            ):
                _sea_den_dime_ranges = [
                    (1, 1, 200.00), (2, 2, 150.00), (3, 3, 100.00), (4, 4, 75.00),
                    (5, 5, 60.00), (6, 6, 50.00), (7, 7, 40.00), (8, 8, 30.00),
                    (9, 9, 25.00), (10, 10, 20.00), (11, 15, 15.00), (16, 20, 10.00),
                    (21, 25, 8.00), (26, 30, 6.00), (31, 40, 5.00), (41, 50, 4.00),
                    (51, 65, 3.00), (66, 85, 2.00), (86, 110, 1.50), (111, 155, 1.00),
                    (156, 275, 0.75), (276, 585, 0.50), (586, 1385, 0.40),
                    (1386, 3670, 0.30), (3671, 11405, 0.20),
                ]
                _sea_den_dime_schedule = np.zeros(11405, dtype=float)
                for _rank_start, _rank_end, _rank_prize in _sea_den_dime_ranges:
                    _sea_den_dime_schedule[_rank_start - 1:_rank_end] = _rank_prize
                # The supplied payout ladder totals exactly $4,000.
                st.session_state["contest_payout_schedule"] = _sea_den_dime_schedule
                st.session_state["contest_payout_source_name"] = "Verified SEA @ DEN $4K Dime Package payout table"
                st.session_state["contest_payout_contest_id"] = _selected_dk_id
                st.session_state["contest_payout_auto_loaded"] = True

            _saved_payouts = st.session_state.get("contest_payout_schedule")
            _current_payout_contest_id = str(st.session_state.get("selected_dk_contest", {}).get("id", ""))
            _payout_matches_selected_contest = (
                bool(_current_payout_contest_id)
                and str(st.session_state.get("contest_payout_contest_id", "")) == _current_payout_contest_id
            )
            if _payout_matches_selected_contest and isinstance(_saved_payouts, np.ndarray) and len(_saved_payouts):
                _paid_positions = int(np.count_nonzero(_saved_payouts > 0))
                _top_prize = float(np.max(_saved_payouts))
                st.success(
                    f"Payout table loaded: {_paid_positions:,} paid finishing positions; "
                    f"top prize ${_top_prize:,.2f}. Source: "
                    f"{st.session_state.get('contest_payout_source_name', 'uploaded CSV')}."
                )
            else:
                st.info("No payout table loaded yet. Contest Sim will show ranking metrics, but projected winnings and ROI will remain unavailable.")




    # ============================================
    # CONTEST SCORING
    # ============================================

    if (
        "contest_field_df" in st.session_state
        and "candidates_df" in st.session_state
        and "simulation_df" in st.session_state
    ):

        contest_field_df = st.session_state["contest_field_df"]
        candidates_df = st.session_state["candidates_df"]
        simulation_df = st.session_state["simulation_df"]

        if candidates_df.empty:
            st.error(
                "No valid candidate lineups were found, so contest scoring cannot run. "
                "Check that enough players have projections, and review any locks, fades, "
                "exposure limits, and salary constraints. Then click SIM again."
            )
            workspace_stop(st, _loaded_slate_tabs)

        if contest_field_df.empty:
            st.error(
                "No simulated opponent lineups were created, so contest scoring cannot run. "
                "Check the selected contest and player pool, then click SIM again."
            )
            workspace_stop(st, _loaded_slate_tabs)

        if platform == "DraftKings" and lineup_mode == "Classic":
            lineup_cols = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
            scoring_multiplier = 1.0
        else:
            lineup_cols = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
            scoring_multiplier = 1.5

        player_index = {
            player: i
            for i, player in enumerate(simulation_df.columns)
        }

        candidate_idx = np.array([
            [player_index[row[col]] for col in lineup_cols]
            for _, row in candidates_df.iterrows()
        ], dtype=np.int16)

        contest_idx = np.array([
            [player_index[row[col]] for col in lineup_cols]
            for _, row in contest_field_df.iterrows()
        ], dtype=np.int16)

        n_candidates = len(candidate_idx)
        n_sims = len(simulation_df)
        selection_n_sims = max(1, n_sims // 2)
        holdout_start = selection_n_sims
        holdout_n_sims = max(1, n_sims - holdout_start)
        total_field = len(contest_idx)
        # The simulated field is a sample. Scale each sampled percentile to the
        # actual contest size before estimating full-field ranks and payouts.
        _selected_contest_for_scoring = st.session_state.get("selected_dk_contest", {}) or {}
        try:
            estimated_full_field_size = int(_selected_contest_for_scoring.get("field_size") or (total_field + 1))
        except (TypeError, ValueError):
            estimated_full_field_size = total_field + 1
        estimated_full_field_size = max(2, estimated_full_field_size)

        st.info(
            f"Step 4 of 4: Scoring {n_candidates:,} candidate lineups against "
            f"{total_field:,} simulated opponents across {n_sims:,} simulations. "
            "This step can take a while for large contests; watch the progress bar below."
        )
        scoring_status = st.empty()
        scoring_status.caption(
            f"Preparing contest scoring arrays for {n_candidates:,} lineups and "
            f"{total_field:,} opponents..."
        )

        win_rates = np.zeros(n_candidates)
        top1_rates = np.zeros(n_candidates)
        top5_rates = np.zeros(n_candidates)
        top10_rates = np.zeros(n_candidates)
        cash_rates = np.zeros(n_candidates)
        avg_percentiles = np.zeros(n_candidates)
        expected_prize_totals = np.zeros(n_candidates, dtype=np.float64)
        payout_schedule = st.session_state.get("contest_payout_schedule")
        _scoring_contest_id = str(st.session_state.get("selected_dk_contest", {}).get("id", ""))
        _payout_belongs_to_scoring_contest = (
            bool(_scoring_contest_id)
            and str(st.session_state.get("contest_payout_contest_id", "")) == _scoring_contest_id
        )
        if _payout_belongs_to_scoring_contest and isinstance(payout_schedule, np.ndarray) and len(payout_schedule):
            payout_schedule = np.asarray(payout_schedule, dtype=np.float64)
        else:
            payout_schedule = None

        if payout_schedule is not None and len(payout_schedule) < estimated_full_field_size:
            st.caption(
                f"Payout estimates use sampled percentiles scaled to an estimated "
                f"{estimated_full_field_size:,}-entry contest. The simulator scores "
                f"{total_field:,} opponents per simulation, so winnings and ROI are estimates, "
                f"not exact full-field results."
            )

        progress = contest_progress_slot.progress(
            0,
            text=(
                f"Step 4 of 4: Scoring contest — 0 of {n_sims:,} simulations (0%) · "
                f"estimated field {estimated_full_field_size:,} entries · "
                f"{total_field:,} opponents scored per simulation"
            ),
        )
        # Convert once and score independent simulation batches concurrently.
        # All simulations and opponents are retained; parallelism changes only how
        # the work is scheduled, not the amount of work performed.
        simulation_values = simulation_df.to_numpy(dtype=np.float32, copy=False)
        batch_size = 128
        batch_ranges = [
            (batch_start, min(batch_start + batch_size, selection_n_sims))
            for batch_start in range(0, selection_n_sims, batch_size)
        ]
        cpu_count = os.cpu_count() or 2
        max_workers = max(1, min(cpu_count, 4, len(batch_ranges)))
        scoring_status.caption(
            f"Scoring {n_sims:,} simulations in parallel using {max_workers} worker threads..."
        )

        def score_batch(batch_start, batch_end):
            batch_values = simulation_values[batch_start:batch_end]
            batch_candidate_scores = batch_values[:, candidate_idx].sum(axis=2)
            batch_field_scores = batch_values[:, contest_idx].sum(axis=2)

            if scoring_multiplier != 1.0:
                batch_candidate_scores += batch_values[:, candidate_idx[:, 0]] * (scoring_multiplier - 1.0)
                batch_field_scores += batch_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)

            # Score the user's portfolio as entries in the SAME contest. Each candidate
            # must compete with the other submitted portfolio entries, not only with
            # simulated opponents. Exclude the candidate itself from its comparison
            # field so the field size remains opponents + the other user entries.
            if n_candidates > 1:
                portfolio_scores = batch_candidate_scores
                combined_scores = np.concatenate((batch_field_scores, portfolio_scores), axis=1)
                sorted_combined = np.sort(combined_scores, axis=1)
            else:
                portfolio_scores = None
                sorted_combined = np.sort(batch_field_scores, axis=1)

            # Sort every simulation's opponent scores together along the opponent axis.
            # Candidate-specific searches below correct for the candidate's own score
            # when the full portfolio was appended to the comparison field.
            sorted_field = sorted_combined

            from simmah_contest_scoring import score_insertion_bounds
            comparison_field_size = total_field + max(0, n_candidates - 1)
            search_field_size = sorted_field.shape[1]
            left_low, low = score_insertion_bounds(sorted_field, batch_candidate_scores)

            count_greater = search_field_size - low
            # The candidate itself is never greater than its own score, so no removal
            # is needed from count_greater. Percentiles use opponents + other entries.
            percentiles = 1.0 - (count_greater / max(1, comparison_field_size))

            # Convert sampled opponent results to a smoothed full-field rank estimate.
            # The +1 continuity correction prevents a lineup that beats every sampled
            # opponent from being treated as a guaranteed first-place finish.
            # Remove the candidate itself from the equal-score count. Other portfolio
            # entries with the same score remain in the tie and therefore split prizes.
            sampled_equal_opponents = np.maximum(0, (low - left_low) - 1)
            sampled_rank_equivalent = count_greater + (0.5 * sampled_equal_opponents)
            # Include duplicate/equal-scoring entries in the rank estimate instead
            # of silently treating every tied lineup as if it had no ties.
            rank_fraction = (sampled_rank_equivalent + 1.0) / (comparison_field_size + 1.0)
            estimated_ranks = 1.0 + rank_fraction * (estimated_full_field_size - 1)
            estimated_ranks = np.clip(estimated_ranks, 1.0, float(estimated_full_field_size))

            # A sampled best score is not a guaranteed win in a much larger contest.
            # Approximate win probability from the estimated chance one field entry
            # outscores this lineup, rather than counting a rounded rank of 1 as a win.
            estimated_tail_probability = np.clip(
                (count_greater + 1.0) / (comparison_field_size + 1.0), 0.0, 1.0
            )
            win_probabilities = np.exp(
                -estimated_tail_probability * max(0, estimated_full_field_size - 1)
            )
            # First place must be a subset of top-1% finishes. The smoothed tail
            # estimate can otherwise produce an impossible Win % greater than Top 1%.
            batch_win = np.minimum(
                np.sum(win_probabilities, axis=0, dtype=np.float64),
                np.sum(percentiles >= 0.99, axis=0, dtype=np.float64),
            )
            batch_top1 = np.sum(percentiles >= 0.99, axis=0, dtype=np.float64)
            batch_top5 = np.sum(percentiles >= 0.95, axis=0, dtype=np.float64)
            batch_top10 = np.sum(percentiles >= 0.90, axis=0, dtype=np.float64)
            batch_percentiles = np.sum(percentiles, axis=0, dtype=np.float64)

            # Estimate the size of each scoring tie from the sampled field, then
            # award the average payout across every rank occupied by that tie.
            # This handles duplicate lineups and other equal-scoring entries more
            # realistically than assigning a single interpolated rank prize.
            paid_positions = (
                min(int(np.count_nonzero(payout_schedule > 0)), estimated_full_field_size)
                if payout_schedule is not None
                else int(np.ceil(estimated_full_field_size * 0.10))
            )
            batch_cash = np.sum(estimated_ranks <= paid_positions, axis=0, dtype=np.float64)
            if payout_schedule is not None and len(payout_schedule) > 0:
                # Scale the observed tie rate from the sampled field to the full
                # contest. A minimum tie size of one preserves ordinary solo ranks.
                estimated_tie_sizes = np.maximum(
                    1,
                    np.rint(
                        (sampled_equal_opponents + 1.0)
                        / (comparison_field_size + 1.0)
                        * estimated_full_field_size
                    ).astype(np.int64),
                )
                tie_start_ranks = np.maximum(
                    1,
                    np.floor(estimated_ranks - (estimated_tie_sizes - 1) / 2.0).astype(np.int64),
                )
                tie_end_ranks = np.minimum(
                    estimated_full_field_size,
                    tie_start_ranks + estimated_tie_sizes - 1,
                )
                rank_axis = np.arange(1, len(payout_schedule) + 1, dtype=np.int64)
                rank_prizes = np.where(rank_axis <= estimated_full_field_size, payout_schedule, 0.0)
                cumulative_prizes = np.concatenate(([0.0], np.cumsum(rank_prizes, dtype=np.float64)))
                safe_start = np.clip(tie_start_ranks - 1, 0, len(payout_schedule))
                safe_end = np.clip(tie_end_ranks, 0, len(payout_schedule))
                prize_sums = cumulative_prizes[safe_end] - cumulative_prizes[safe_start]
                # Divide by every rank occupied by the tie, including unpaid ranks.
                # Any tied positions beyond the payout schedule receive $0, so a tie
                # that crosses the cash line shares the available prizes with those
                # unpaid positions instead of overstating expected winnings.
                batch_prizes = np.divide(
                    prize_sums,
                    estimated_tie_sizes,
                    out=np.zeros_like(prize_sums, dtype=np.float64),
                    where=estimated_tie_sizes > 0,
                )
                batch_prize_totals = np.sum(batch_prizes, axis=0, dtype=np.float64)
            else:
                batch_prize_totals = np.zeros(n_candidates, dtype=np.float64)

            return batch_win, batch_top1, batch_top5, batch_top10, batch_cash, batch_percentiles, batch_prize_totals

        completed_batches = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(score_batch, batch_start, batch_end): (batch_start, batch_end)
                for batch_start, batch_end in batch_ranges
            }
            for future in as_completed(futures):
                batch_win, batch_top1, batch_top5, batch_top10, batch_cash, batch_percentiles, batch_prize_totals = future.result()
                win_rates += batch_win
                top1_rates += batch_top1
                top5_rates += batch_top5
                top10_rates += batch_top10
                cash_rates += batch_cash
                avg_percentiles += batch_percentiles
                expected_prize_totals += batch_prize_totals
                completed_batches += 1
                completed_sims = min(completed_batches * batch_size, n_sims)
                progress.progress(
                    completed_batches / len(batch_ranges),
                    text=(
                        f"Step 4 of 4: Scoring contest — {completed_sims:,} of {n_sims:,} "
                        f"simulations ({completed_sims / n_sims:.0%}) using {max_workers} workers · "
                        f"estimated field {estimated_full_field_size:,} entries · "
                        f"{total_field:,} opponents per simulation"
                    ),
                )

        progress.empty()
        scoring_status.caption("Scoring complete. Building the ranked results table...")

        results_df = candidates_df.copy()

        results_df["WinRate"] = win_rates / selection_n_sims
        results_df["Top1"] = top1_rates / selection_n_sims
        results_df["Top5"] = top5_rates / selection_n_sims
        results_df["Top10"] = top10_rates / selection_n_sims
        results_df["CashRate"] = cash_rates / selection_n_sims
        results_df["AvgPercentile"] = avg_percentiles / selection_n_sims

        # Diagnostic only: show whether the selected candidates keep their advantage
        # on the untouched second half of simulations. A large drop from Selection to
        # Holdout points to selection overfitting rather than a weak opponent field.
        if holdout_n_sims > 0 and n_candidates > 0:
            _diag_count = min(20, n_candidates)
            _diag_idx = np.arange(_diag_count, dtype=np.int32)
            _diag_candidate_idx = candidate_idx[_diag_idx]
            _diag_top1 = np.zeros(_diag_count, dtype=np.float64)
            _diag_top5 = np.zeros(_diag_count, dtype=np.float64)
            _diag_top10 = np.zeros(_diag_count, dtype=np.float64)
            _diag_cash = np.zeros(_diag_count, dtype=np.float64)
            _diag_pct = np.zeros(_diag_count, dtype=np.float64)
            _diag_batch_size = 128
            for _diag_start in range(holdout_start, n_sims, _diag_batch_size):
                _diag_end = min(_diag_start + _diag_batch_size, n_sims)
                _diag_values = simulation_values[_diag_start:_diag_end]
                _diag_scores = _diag_values[:, _diag_candidate_idx].sum(axis=2)
                _diag_field_scores = _diag_values[:, contest_idx].sum(axis=2)
                if scoring_multiplier != 1.0:
                    _diag_scores[:, :] += _diag_values[:, _diag_candidate_idx[:, 0]] * (scoring_multiplier - 1.0)
                    _diag_field_scores[:, :] += _diag_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)
                _diag_sorted = np.sort(_diag_field_scores, axis=1)
                _diag_greater = np.empty_like(_diag_scores, dtype=np.float64)
                for _r in range(_diag_scores.shape[0]):
                    _diag_greater[_r] = total_field - np.searchsorted(_diag_sorted[_r], _diag_scores[_r], side="right")
                _diag_percentiles = 1.0 - (_diag_greater / max(1, total_field))
                _diag_top1 += np.sum(_diag_percentiles >= 0.99, axis=0)
                _diag_top5 += np.sum(_diag_percentiles >= 0.95, axis=0)
                _diag_top10 += np.sum(_diag_percentiles >= 0.90, axis=0)
                _diag_cash += np.sum(_diag_percentiles >= 0.50, axis=0)
                _diag_pct += np.sum(_diag_percentiles, axis=0)
            _selection_slice = results_df.iloc[:_diag_count] if "results_df" in locals() else None
            st.session_state["contest_holdout_diagnostic"] = {
                "lineups": int(_diag_count),
                "holdout_sims": int(holdout_n_sims),
                "top1": float(np.mean(_diag_top1 / holdout_n_sims)),
                "top5": float(np.mean(_diag_top5 / holdout_n_sims)),
                "top10": float(np.mean(_diag_top10 / holdout_n_sims)),
                "cash": float(np.mean(_diag_cash / holdout_n_sims)),
                "avg_percentile": float(np.mean(_diag_pct / holdout_n_sims)),
            }

        # Field sanity baseline: 20 random opponent lineups should land near 1/5/10%.
        _sanity_n=min(20,total_field)
        if _sanity_n:
            _rng=np.random.default_rng(20261014); _idx=contest_idx[_rng.choice(total_field,_sanity_n,replace=False)]; _counts=np.zeros(4); _obs=0
            for _start in range(0,selection_n_sims,batch_size):
                _end=min(_start+batch_size,selection_n_sims); _v=simulation_values[_start:_end]; _s=_v[:,_idx].sum(axis=2); _f=_v[:,contest_idx].sum(axis=2)
                if scoring_multiplier != 1.0:
                    _s += _v[:,_idx[:,0]]*(scoring_multiplier-1.0); _f += _v[:,contest_idx[:,0]]*(scoring_multiplier-1.0)
                _sorted=np.sort(_f,axis=1); _greater=total_field-np.sum(_sorted[:,:,None] <= _s[:,None,:],axis=1); _pct=1.0-_greater/max(1,total_field)
                _counts += [np.sum(_pct>=.99),np.sum(_pct>=.95),np.sum(_pct>=.90),np.sum(_pct>=.50)]; _obs += _pct.size
            st.session_state["field_sanity_check"]={"Lineups":_sanity_n,"Top 1%":100*_counts[0]/_obs,"Top 5%":100*_counts[1]/_obs,"Top 10%":100*_counts[2]/_obs,"Cash %":100*_counts[3]/_obs}

        if payout_schedule is not None:
            results_df["Expected Prize ($)"] = expected_prize_totals / selection_n_sims
            selected_contest_for_payout = st.session_state.get("selected_dk_contest", {})
            entry_fee_for_payout = pd.to_numeric(
                selected_contest_for_payout.get("entry_fee"), errors="coerce"
            )
            if pd.notna(entry_fee_for_payout) and float(entry_fee_for_payout) >= 0:
                results_df["Expected Net ($)"] = results_df["Expected Prize ($)"] - float(entry_fee_for_payout)
                results_df["Expected ROI (%)"] = np.where(
                    float(entry_fee_for_payout) > 0,
                    results_df["Expected Net ($)"] / float(entry_fee_for_payout) * 100.0,
                    np.nan
                )

        results_df["ContestScore"] = (
            results_df["Top1"] * 0.40
            + results_df["Top5"] * 0.25
            + results_df["Top10"] * 0.20
            + results_df["CashRate"] * 0.10
            + results_df["WinRate"] * 0.05
        )

        results_df = (
            results_df
            .sort_values("ContestScore", ascending=False, kind="stable")
            .reset_index(drop=True)
        )

        # Save immediately so the ranked results survive later UI rendering or reruns.
        st.session_state["contest_results_df"] = results_df
        if payout_schedule is not None:
            _paid_positions_for_notice = int(np.count_nonzero(payout_schedule > 0))
            if estimated_full_field_size < _paid_positions_for_notice:
                st.warning(
                    f"The payout table pays {_paid_positions_for_notice:,} places, but the entered contest size is "
                    f"{estimated_full_field_size:,}. Cash rate, prize, and ROI estimates may not match the selected contest."
                )
            else:
                st.success(
                    f"Expected Prize and ROI use the selected payout table and estimated ranks in a "
                    f"{estimated_full_field_size:,}-entry contest. The opponent field is sampled "
                    f"({total_field:,} per simulation), so results are estimates, not guaranteed winnings."
                )
        if build_clicked:
            # A fresh build must create a fresh user pool instead of carrying over
            # lineups or exposure state from the previous build.
            for _key in (
                "portfolio_df",
                "portfolio_count_used",
                "portfolio_metric_used",
                "portfolio_control_signature",
            ):
                st.session_state.pop(_key, None)
        scoring_status.success(f"Ranking complete — {len(results_df):,} lineups ranked. Loading your portfolio below.")
        _sanity=st.session_state.get("field_sanity_check")
        if isinstance(_sanity,dict):
            st.write("### Field Sanity Check")
            st.caption("20 random simulated opponent lineups. Normal baseline: about 1% / 5% / 10% for Top 1 / Top 5 / Top 10.")
            st.dataframe(injury_frame(st, pd.DataFrame([_sanity])),use_container_width=True,hide_index=True)

    # ============================================

    # ============================================
    # PORTFOLIO FUNCTIONS
    # ============================================

    def build_portfolio(results_df, lineup_count, metric, lineup_columns=None):
        """Build a ranked portfolio for either Classic or Showdown."""
        if lineup_count < 1:
            raise ValueError("Lineup count must be at least 1.")
        if metric not in results_df.columns:
            raise ValueError(f"Ranking metric not found: {metric}")
        if lineup_columns is None:
            lineup_columns = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        lineup_columns = [col for col in lineup_columns if col in results_df.columns]
        if not lineup_columns:
            raise ValueError("Could not identify lineup roster columns.")
        ranked = results_df.drop_duplicates(subset=lineup_columns, keep="first").copy()
        ranked[metric] = pd.to_numeric(ranked[metric], errors="coerce").fillna(0.0)
        metric_min = float(ranked[metric].min()) if not ranked.empty else 0.0
        metric_max = float(ranked[metric].max()) if not ranked.empty else 0.0
        if metric_max > metric_min:
            ranked["_portfolio_quality"] = (ranked[metric] - metric_min) / (metric_max - metric_min)
        else:
            ranked["_portfolio_quality"] = 1.0
        player_counts, captain_counts, selected_rows = {}, {}, []
        selected_player_sets = []

        def exposure_limit(player, setting, default=100):
            settings = control_map.get(str(player), {})
            try:
                percent = float(settings.get(setting, default))
            except (TypeError, ValueError):
                percent = float(default)
            if percent <= 0:
                return 0
            return max(1, int(np.ceil(lineup_count * min(100.0, percent) / 100.0)))

        captain_col = "Captain" if "Captain" in lineup_columns else None
        # Greedily balance lineup quality with uniqueness. The overlap penalty is
        # normalized, so it behaves consistently across win-rate and score metrics.
        remaining = ranked.copy()
        while len(selected_rows) < lineup_count and not remaining.empty:
            best_index = None
            best_value = -float("inf")
            for idx, row in remaining.iterrows():
                names = [str(row[col]) for col in lineup_columns]
                unique_names = set(names)
                if any(player_counts.get(name, 0) >= exposure_limit(name, "Max Exposure %") for name in unique_names):
                    continue
                captain = str(row[captain_col]) if captain_col else None
                if captain_col and captain_counts.get(captain, 0) >= exposure_limit(captain, "Captain Max %"):
                    continue
                if selected_player_sets:
                    overlap = max(
                        len(unique_names & prior) / max(1, len(unique_names))
                        for prior in selected_player_sets
                    )
                else:
                    overlap = 0.0
                selection_value = float(row["_portfolio_quality"]) - 0.20 * overlap
                if selection_value > best_value:
                    best_value = selection_value
                    best_index = idx
            if best_index is None:
                break
            row = remaining.loc[best_index]
            names = [str(row[col]) for col in lineup_columns]
            unique_names = set(names)
            captain = str(row[captain_col]) if captain_col else None
            selected_rows.append(row.drop(labels=["_portfolio_quality"]).copy())
            selected_player_sets.append(unique_names)
            for name in unique_names:
                player_counts[name] = player_counts.get(name, 0) + 1
            if captain_col:
                captain_counts[captain] = captain_counts.get(captain, 0) + 1
            remaining = remaining.drop(index=best_index)

        if not selected_rows:
            raise ValueError("No lineups fit the current exposure limits. Increase Max Exposure % and try again.")
        portfolio = pd.DataFrame(selected_rows).reset_index(drop=True)
        portfolio["Locked"] = False
        if len(portfolio) < lineup_count:
            st.warning(f"Exposure limits allowed {len(portfolio)} of {lineup_count} requested lineups. Raise some Max Exposure % limits to allow more.")
        return portfolio

    def lock_portfolio_lineup(portfolio_df, lineup_index):
        """Lock one lineup so it cannot be replaced."""

        portfolio_df = portfolio_df.copy()

        if 0 <= lineup_index < len(portfolio_df):
            portfolio_df.loc[lineup_index, "Locked"] = True

        return portfolio_df


    def delete_and_replace_portfolio_lineup(
        portfolio_df,
        results_df,
        lineup_index,
        metric,
        lineup_columns=None
    ):
        """Delete one unlocked lineup and replace it with the next ranked lineup."""

        portfolio_df = portfolio_df.copy()

        if not 0 <= lineup_index < len(portfolio_df):
            return portfolio_df

        if bool(portfolio_df.loc[lineup_index, "Locked"]):
            return portfolio_df

        if lineup_columns is None:
            lineup_columns = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        lineup_columns = [col for col in lineup_columns if col in portfolio_df.columns and col in results_df.columns]
        if not lineup_columns:
            return portfolio_df.reset_index(drop=True)

        deleted_key = tuple(
            portfolio_df.loc[
                lineup_index,
                lineup_columns
            ]
        )

        remaining = portfolio_df.drop(
            portfolio_df.index[lineup_index]
        ).copy()

        used_keys = set(
            tuple(row)
            for row in remaining[lineup_columns].to_numpy()
        )

        ranked = results_df.sort_values(
            metric,
            ascending=False
        )

        replacement = None

        for _, row in ranked.iterrows():

            key = tuple(
                row[lineup_columns]
            )

            if key not in used_keys and key != deleted_key:
                replacement = row.copy()
                break

        if replacement is not None:
            replacement["Locked"] = False

            remaining = pd.concat(
                [
                    remaining,
                    replacement.to_frame().T
                ],
                ignore_index=True
            )

        return remaining.reset_index(drop=True)


    # ============================================
    # ============================================
    # PORTFOLIO
    # ============================================

    st.divider()
    st.write("## Portfolio")

    # Save the generated opponent field before it is lost from this browser session.
    # Classic uses its own field key; Showdown and other formats use contest_field_df.
    _saved_field_key = (
        "classic_contest_field_df"
        if platform == "DraftKings" and lineup_mode == "Classic"
        else "fd_full_contest_field_df"
        if platform == "FanDuel" and lineup_mode == "Full Roster"
        else "contest_field_df"
    )
    _saved_field_df = st.session_state.get(_saved_field_key)
    _saved_sample_df = st.session_state.get(
        "classic_contest_field_sample_df"
        if platform == "DraftKings" and lineup_mode == "Classic"
        else "fd_full_contest_field_sample_df"
        if platform == "FanDuel" and lineup_mode == "Full Roster"
        else "contest_field_sample_df"
    )
    if isinstance(_saved_field_df, pd.DataFrame) and not _saved_field_df.empty:
        st.write("### Save Simulated Opponent Lineups")
        st.caption(
            "Download these estimated opponent lineups now so you can compare them "
            "with your actual contest results later. The field is an estimate, not "
            "the actual lineups submitted by other DraftKings players."
        )
        _field_csv = _saved_field_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Full Simulated Opponent Field (CSV)",
            data=_field_csv,
            file_name=f"simulated_opponent_field_{lineup_mode.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            key="download_simulated_opponent_field"
        )
        if isinstance(_saved_sample_df, pd.DataFrame) and not _saved_sample_df.empty:
            _sample_csv = _saved_sample_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Representative Field Sample (CSV)",
                data=_sample_csv,
                file_name=f"simulated_opponent_sample_{lineup_mode.lower().replace(' ', '_')}.csv",
                mime="text/csv",
                key="download_simulated_opponent_sample"
            )

    if "contest_results_df" in st.session_state and not (platform == "DraftKings" and lineup_mode == "Classic"):

        results_df = st.session_state["contest_results_df"]
        if platform == "DraftKings" and lineup_mode == "Showdown":
            render_value_leverage_finder(control_display, results_df, st.session_state.get("contest_field_df"),
                ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"], "dk_showdown", "Captain")
        classic_mode = platform == "DraftKings" and lineup_mode == "Classic"
        portfolio_lineup_columns = (
            ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
            if classic_mode else ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        )
        portfolio_lineup_columns = [col for col in portfolio_lineup_columns if col in results_df.columns]
        st.caption("Generate 5,000 candidates, then select up to 20 final lineups for your contest.")

        portfolio_limit = min(20, len(results_df))
        portfolio_count = st.number_input(
            "Number of lineups to show",
            min_value=1,
            max_value=max(1, portfolio_limit),
            value=max(1, portfolio_limit),
            step=1,
            key="portfolio_count"
        )

        portfolio_metric_label = st.selectbox(
            "Rank lineups by",
            list(PORTFOLIO_METRICS.keys()),
            index=list(PORTFOLIO_METRICS.keys()).index("Top 1%"),
            key="portfolio_metric_top1_default_v2"
        )

        portfolio_metric = PORTFOLIO_METRICS[
            portfolio_metric_label
        ]

        current_control_signature = tuple(
            sorted(
                (
                    str(name),
                    float(values.get("Max Exposure %", 100)),
                    float(values.get("Captain Max %", 100)),
                    float(values.get("Min Exposure %", 0)),
                    float(values.get("Captain Min %", 0)),
                    bool(values.get("Lock", False)),
                    bool(values.get("Fade", False))
                )
                for name, values in control_map.items()
            )
        )
        if (
            "portfolio_df" not in st.session_state
            or st.session_state.get("portfolio_count_used") != portfolio_count
            or st.session_state.get("portfolio_control_signature") != current_control_signature
            or st.session_state.get("portfolio_metric_used") != portfolio_metric
            or st.session_state.get("portfolio_exposure_diversity_used") != portfolio_diversity
        ):

            from simmah_portfolio_selection import select_portfolio
            try:
                portfolio_df = select_portfolio(results_df, portfolio_lineup_columns,
                    int(portfolio_count), portfolio_metric, controls=control_map,
                    diversity=portfolio_diversity)
            except ValueError as exc:
                st.error(str(exc))
                workspace_stop(st, _loaded_slate_tabs)
            portfolio_df["Locked"] = False
            if portfolio_df.attrs.get("effective_auto_cap_pct",100) > (100-.4*portfolio_diversity):
                st.warning(f"Automatic exposure cap increased to {portfolio_df.attrs['effective_auto_cap_pct']}% to fill entries. Manual limits remain enforced.")

            st.session_state["portfolio_df"] = portfolio_df
            st.session_state["portfolio_count_used"] = portfolio_count
            st.session_state["portfolio_metric_used"] = portfolio_metric
            st.session_state["portfolio_control_signature"] = current_control_signature
            st.session_state["portfolio_exposure_diversity_used"] = portfolio_diversity

        # Changing the sort option must reorder the existing pool, not select a new one.
        # This keeps the exact same lineups while letting the user inspect a different ranking.
        portfolio_df = st.session_state["portfolio_df"].copy()
        # Keep saved/restored portfolio rows mathematically consistent too.
        if "WinRate" in portfolio_df.columns and "Top1" in portfolio_df.columns:
            portfolio_df["WinRate"] = np.minimum(
                pd.to_numeric(portfolio_df["WinRate"], errors="coerce").fillna(0.0),
                pd.to_numeric(portfolio_df["Top1"], errors="coerce").fillna(0.0),
            )
        if portfolio_metric in portfolio_df.columns:
            portfolio_df = portfolio_df.sort_values(
                portfolio_metric, ascending=False, kind="stable"
            ).reset_index(drop=True)
        st.session_state["portfolio_df"] = portfolio_df.copy()
        st.session_state["portfolio_metric_used"] = portfolio_metric
        with _tab_lineups:
            portfolio_df = render_editor(st, portfolio_df, players_df, portfolio_lineup_columns,
                "DraftKings", "Showdown", st.session_state.get("selected_dk_contest", {}),
                validator=single_stack_validator(st, "DraftKings", "Showdown", full_roster_stack_lookup(players_df)))
        portfolio_df = add_lineup_field_ownership(portfolio_df)

        # Add each lineup's total salary to the portfolio display and export.
        if classic_mode:
            portfolio_df["Salary"] = portfolio_df.apply(
                lambda row: int(sum(salary_map.get(str(row.get(col, "")), 0) for col in portfolio_lineup_columns)),
                axis=1
            )
        else:
            portfolio_df["Salary"] = portfolio_df.apply(
                lambda row: int(
                    captain_salary_map.get(str(row.get("Captain", "")), 0)
                    + sum(salary_map.get(str(row.get(col, "")), 0) for col in ["Flex1", "Flex2", "Flex3", "Flex4", "Flex5"])
                ),
                axis=1
            )
        st.session_state["portfolio_df"] = portfolio_df

        # Show each rostered player's average score across the player simulations.
        # For the Showdown captain, apply the 1.5x scoring multiplier.
        sim_scores = st.session_state.get("simulation_df")
        if isinstance(sim_scores, pd.DataFrame) and not sim_scores.empty:
            sim_player_means = sim_scores.mean(axis=0, numeric_only=True).to_dict()
            for slot in portfolio_lineup_columns:
                if slot not in portfolio_df.columns:
                    continue
                multiplier = 1.5 if slot == "Captain" else 1.0
                score_col = slot + " Sim Pts"
                portfolio_df[score_col] = portfolio_df[slot].map(
                    lambda player: round(float(sim_player_means.get(str(player), 0.0)) * multiplier, 2)
                )
            sim_point_columns = [
                slot + " Sim Pts"
                for slot in portfolio_lineup_columns
                if slot + " Sim Pts" in portfolio_df.columns
            ]
            portfolio_df["Total Sim Pts"] = portfolio_df[sim_point_columns].apply(
                pd.to_numeric, errors="coerce"
            ).sum(axis=1).round(2)
            st.session_state["portfolio_df"] = portfolio_df

        st.write(
            f"Portfolio: {len(portfolio_df)} lineups"
        )
        if "Lineup Ownership Score (%)" in portfolio_df.columns:
            st.caption("Lineup Ownership Score is the sum of each player's simulated ownership in the contest field. Lower scores generally mean a less popular lineup; this is a score, not the chance the exact lineup appears.")

        # Add the selected contest entry fee beside each lineup when available.
        selected_contest_for_portfolio = st.session_state.get("selected_dk_contest", {})
        _portfolio_entry_fee = pd.to_numeric(
            selected_contest_for_portfolio.get("entry_fee"), errors="coerce"
        )
        if pd.notna(_portfolio_entry_fee) and float(_portfolio_entry_fee) >= 0:
            portfolio_df["Entry Fee ($)"] = float(_portfolio_entry_fee)

        # Score the selected portfolio jointly. Each simulation compares every selected
        # entry with the sampled opponent field AND with the user's other entries.
        # This avoids simply adding independent per-lineup estimates that ignore
        # portfolio overlap and ties among the user's own entries.
        if pd.notna(_portfolio_entry_fee):
            _portfolio_lineup_count = len(portfolio_df)
            _portfolio_total_fees = _portfolio_lineup_count * float(_portfolio_entry_fee)
            _portfolio_prize_schedule = st.session_state.get("contest_payout_schedule")
            _portfolio_contest_id = str(st.session_state.get("selected_dk_contest", {}).get("id", ""))
            _portfolio_payout_is_valid = (
                bool(_portfolio_contest_id)
                and str(st.session_state.get("contest_payout_contest_id", "")) == _portfolio_contest_id
                and isinstance(_portfolio_prize_schedule, np.ndarray)
                and len(_portfolio_prize_schedule) > 0
            )
            if _portfolio_payout_is_valid and _portfolio_lineup_count > 0:
                _portfolio_slot_indices = np.array([
                    [player_index[str(row[col])] for col in lineup_cols]
                    for _, row in portfolio_df.iterrows()
                ], dtype=np.int16)
                _portfolio_prize_totals = np.zeros(_portfolio_lineup_count, dtype=np.float64)
                _portfolio_batch_size = 128
                _portfolio_full_size = int(max(2, estimated_full_field_size))
                _portfolio_rank_axis = np.arange(1, len(_portfolio_prize_schedule) + 1, dtype=np.int64)
                _portfolio_rank_prizes = np.where(
                    _portfolio_rank_axis <= _portfolio_full_size,
                    _portfolio_prize_schedule,
                    0.0,
                )
                _portfolio_cumulative_prizes = np.concatenate((
                    [0.0], np.cumsum(_portfolio_rank_prizes, dtype=np.float64)
                ))
                _field_cache_owner, _portfolio_cached_field = showdown_sorted_field_cached(
                    simulation_values, contest_idx, scoring_multiplier, holdout_start, n_sims)
                for _portfolio_batch_start in range(holdout_start, n_sims, _portfolio_batch_size):
                    _portfolio_batch_end = min(_portfolio_batch_start + _portfolio_batch_size, n_sims)
                    _portfolio_values = simulation_values[_portfolio_batch_start:_portfolio_batch_end]
                    _portfolio_scores = _portfolio_values[:, _portfolio_slot_indices].sum(axis=2)
                    if scoring_multiplier != 1.0:
                        _portfolio_scores += (
                            _portfolio_values[:, _portfolio_slot_indices[:, 0]]
                            * (scoring_multiplier - 1.0)
                        )
                    # Field scores are unchanged when exposure diversity changes.
                    _portfolio_sorted_field = _portfolio_cached_field[
                        _portfolio_batch_start-holdout_start:_portfolio_batch_end-holdout_start]
                    _portfolio_batch_count = _portfolio_batch_end - _portfolio_batch_start
                    _portfolio_sim_rows = np.arange(_portfolio_batch_count)[:, None]

                    # Right insertion point = number of field scores <= each user lineup.
                    _portfolio_low = np.zeros(
                        (_portfolio_batch_count, _portfolio_lineup_count), dtype=np.int32
                    )
                    _portfolio_high = np.full_like(_portfolio_low, total_field)
                    while np.any(_portfolio_low < _portfolio_high):
                        _active = _portfolio_low < _portfolio_high
                        _mid = (_portfolio_low + _portfolio_high) // 2
                        _mid_values = _portfolio_sorted_field[_portfolio_sim_rows, np.minimum(_mid, total_field - 1)]
                        _move_right = (_mid_values <= _portfolio_scores) & _active
                        _move_left = (_mid_values > _portfolio_scores) & _active
                        _portfolio_low = np.where(_move_right, _mid + 1, _portfolio_low)
                        _portfolio_high = np.where(_move_left, _mid, _portfolio_high)

                    # Left insertion point = number of field scores strictly below each lineup.
                    _portfolio_left = np.zeros_like(_portfolio_low)
                    _portfolio_left_high = np.full_like(_portfolio_left, total_field)
                    while np.any(_portfolio_left < _portfolio_left_high):
                        _active_left = _portfolio_left < _portfolio_left_high
                        _mid_left = (_portfolio_left + _portfolio_left_high) // 2
                        _mid_left_values = _portfolio_sorted_field[
                            _portfolio_sim_rows, np.minimum(_mid_left, total_field - 1)
                        ]
                        _move_right_left = (_mid_left_values < _portfolio_scores) & _active_left
                        _move_left_left = (_mid_left_values >= _portfolio_scores) & _active_left
                        _portfolio_left = np.where(_move_right_left, _mid_left + 1, _portfolio_left)
                        _portfolio_left_high = np.where(_move_left_left, _mid_left, _portfolio_left_high)

                    _greater_field = total_field - _portfolio_low
                    _equal_field = _portfolio_low - _portfolio_left
                    # Compare the user's small portfolio internally; this matrix is only
                    # entries-by-entries, not opponents-by-entries.
                    _greater_own = np.sum(
                        _portfolio_scores[:, None, :] > _portfolio_scores[:, :, None], axis=2
                    )
                    _equal_own = np.sum(
                        _portfolio_scores[:, None, :] == _portfolio_scores[:, :, None], axis=2
                    ) - 1
                    _sampled_greater = _greater_field + _greater_own
                    _sampled_ties = _equal_field + _equal_own
                    _rank_fraction = (_sampled_greater + 0.5 * _sampled_ties + 1.0) / (total_field + 1.0)
                    _estimated_ranks = np.clip(
                        1.0 + _rank_fraction * (_portfolio_full_size - 1),
                        1.0,
                        float(_portfolio_full_size),
                    )
                    _estimated_tie_sizes = np.maximum(
                        1,
                        np.rint(
                            (_sampled_ties + 1.0) / (total_field + _portfolio_lineup_count + 1.0)
                            * _portfolio_full_size
                        ).astype(np.int64),
                    )
                    _tie_start = np.maximum(
                        1,
                        np.floor(_estimated_ranks - (_estimated_tie_sizes - 1) / 2.0).astype(np.int64),
                    )
                    _tie_end = np.minimum(
                        _portfolio_full_size,
                        _tie_start + _estimated_tie_sizes - 1,
                    )
                    _safe_start = np.clip(_tie_start - 1, 0, len(_portfolio_cumulative_prizes) - 1)
                    _safe_end = np.clip(_tie_end, 0, len(_portfolio_cumulative_prizes) - 1)
                    _tie_prize_sum = _portfolio_cumulative_prizes[_safe_end] - _portfolio_cumulative_prizes[_safe_start]
                    _portfolio_prize_totals += np.sum(
                        np.divide(
                            _tie_prize_sum,
                            _estimated_tie_sizes,
                            out=np.zeros_like(_tie_prize_sum, dtype=np.float64),
                            where=_estimated_tie_sizes > 0,
                        ),
                        axis=0,
                    )
                portfolio_df["Expected Prize ($)"] = _portfolio_prize_totals / holdout_n_sims
                portfolio_df["Expected Net ($)"] = portfolio_df["Expected Prize ($)"] - float(_portfolio_entry_fee)
                portfolio_df["Expected ROI (%)"] = np.where(
                    float(_portfolio_entry_fee) > 0,
                    portfolio_df["Expected Net ($)"] / float(_portfolio_entry_fee) * 100.0,
                    np.nan,
                )
                st.session_state["portfolio_df"] = portfolio_df
                _portfolio_total_prizes = float(_portfolio_prize_totals.sum() / holdout_n_sims)
                _portfolio_expected_net = _portfolio_total_prizes - _portfolio_total_fees
                _portfolio_expected_roi = (
                    _portfolio_expected_net / _portfolio_total_fees * 100.0
                    if _portfolio_total_fees > 0 else np.nan
                )
                st.caption(
                    "Holdout portfolio estimate: lineups are selected using one half of the simulations, then "
                    "ROI is measured on the untouched second half. Entries are scored together and ties are split. "
                    "Full-field ranks and winnings remain estimates."
                )
            else:
                st.info(
                    "Joint portfolio winnings are not available because a payout schedule has not been confirmed "
                    "for the selected contest. Upload or select the correct contest payout table to calculate ROI."
                )

        if not classic_mode and "Captain" in portfolio_df.columns:
            from simmah_duplicates import showdown_opponent_copies
            portfolio_df = portfolio_df.drop(columns=["Projected Dupes"], errors="ignore")
            portfolio_df["Simulated Opponent Copies"] = showdown_opponent_copies(
                portfolio_df, st.session_state.get("contest_field_df")
            )

        render_portfolio_roi_panel(portfolio_df, st.session_state.get("selected_dk_contest"))
        _payout_columns = ["Expected Prize ($)", "Expected Net ($)", "Expected ROI (%)"]
        if classic_mode:
            # Show each Classic roster slot beside that player's simulated points,
            # matching the player-by-player layout used for Showdown.
            display_columns = []
            for slot in portfolio_lineup_columns:
                display_columns.extend([slot, slot + " Sim Pts"])
            display_columns.extend([
                "Total Sim Pts", "Lineup Ownership Score (%)", "Salary",
                "ContestScore", "WinRate", "Top1", "Top5", "Top10", "CashRate",
                "AvgPercentile", "Entry Fee ($)", *_payout_columns, "Locked"
            ])
        else:
            display_columns = [
                "Captain", "Captain Sim Pts", "Flex1", "Flex1 Sim Pts",
                "Flex2", "Flex2 Sim Pts", "Flex3", "Flex3 Sim Pts",
                "Flex4", "Flex4 Sim Pts", "Flex5", "Flex5 Sim Pts",
                "Total Sim Pts", "Lineup Ownership Score (%)", "Salary", "Simulated Opponent Copies",
                "ContestScore", "WinRate", "Top1", "Top5", "Top10", "CashRate",
                "AvgPercentile", "Entry Fee ($)", *_payout_columns, "Locked"
            ]

        display_df = portfolio_df[
            [c for c in display_columns if c in portfolio_df.columns]
        ].copy()

        # Show every ranking option as a column in the actual portfolio, not just
        # the metric currently selected in the ranking dropdown.
        for col in [
            "ContestScore",
            "WinRate",
            "Top1",
            "Top5",
            "Top10",
            "CashRate"
        ]:
            if col in display_df.columns:
                display_df[col] = display_df[col] * 100

        display_df = display_df.rename(columns={
            "ContestScore": "Contest Score",
            "WinRate": "Win %",
            "Top1": "Top 1%",
            "Top5": "Top 5%",
            "Top10": "Top 10%",
            "CashRate": "Cash %",
            "AvgPercentile": "Average Percentile",
        })

        st.write("### Assigned contest portfolio")

        st.dataframe(
            injury_frame(st, display_df),
            use_container_width=True,
            hide_index=True
        )

        if not classic_mode:
            st.caption("Simulated Opponent Copies counts matching opponents in the current simulated field, with Captain fixed and FLEX order ignored. It excludes your own entries and is not a forecast of actual contest duplicates.")

        # Final portfolio exposure is shown in the Player Pool table, so no separate table is built here.

        export_columns = [
            "Captain", "Captain Sim Pts", "Flex1", "Flex1 Sim Pts",
            "Flex2", "Flex2 Sim Pts", "Flex3", "Flex3 Sim Pts",
            "Flex4", "Flex4 Sim Pts", "Flex5", "Flex5 Sim Pts",
            "Salary", "Lineup Ownership Score (%)", "Simulated Opponent Copies", "ContestScore", "WinRate", "Top1", "Top5",
            "Top10", "CashRate", "Entry Fee ($)", "Expected Prize ($)", "Expected Net ($)",
            "Expected ROI (%)"
        ]
        portfolio_df = remove_out_players_from_lineups(
            portfolio_df,
            portfolio_lineup_columns,
            "portfolio export"
        )
        st.session_state["portfolio_df"] = portfolio_df
        portfolio_export_df = portfolio_df[
            [col for col in export_columns if col in portfolio_df.columns]
        ].copy()

        # Include the selected contest number/name in analysis exports too.
        # Keep these metadata columns out of DraftKings roster-upload templates.
        selected_dk_contest = st.session_state.get("selected_dk_contest", {})
        if isinstance(selected_dk_contest, dict):
            contest_id = selected_dk_contest.get("id")
            contest_name = selected_dk_contest.get("name")
            if contest_id not in (None, ""):
                portfolio_export_df.insert(0, "Contest ID", str(contest_id))
            if contest_name not in (None, ""):
                insert_at = 1 if "Contest ID" in portfolio_export_df.columns else 0
                portfolio_export_df.insert(insert_at, "Contest Name", str(contest_name))

        for col in ["WinRate", "Top1", "Top5", "Top10", "CashRate"]:
            if col in portfolio_export_df.columns:
                portfolio_export_df[col] = portfolio_export_df[col] * 100

        lineup_export_download(
            label="DOWNLOAD ASSIGNED PORTFOLIO REPORT",
            data=portfolio_export_df.to_csv(index=False).encode("utf-8"),
            file_name="DraftKings_Showdown_Assigned_Portfolio.csv",
            mime="text/csv",
            use_container_width=True,
            on_click="ignore"
        )


    else:
        st.info(
            "Run CONTEST SIM before building a portfolio."
        )


    # ============================================
    # ============================================
    # DRAFTKINGS SHOWDOWN EXPORT BUTTON
    # Export the selected final portfolio using CPT and FLEX IDs from the uploaded DK template.
    with st.container():
        if platform == "DraftKings" and lineup_mode == "Showdown":
            render_entry_export_header("DraftKings")
            export_portfolio = st.session_state.get("portfolio_df")
            export_portfolio = remove_out_players_from_lineups(
                export_portfolio, ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"], "DraftKings Showdown export"
            )
            if isinstance(export_portfolio, pd.DataFrame):
                st.session_state["portfolio_df"] = export_portfolio
            dk_player_ids = st.session_state.get("dk_player_ids", {})
            if isinstance(export_portfolio, pd.DataFrame) and not export_portfolio.empty:
                if not dk_player_ids:
                    st.warning("Upload the DraftKings Showdown lineup template CSV first so the app can get the CPT/FLEX player IDs.")
                else:
                    export_rows = []
                    missing_ids = []
                    for _, row in export_portfolio.iterrows():
                        captain = str(row.get("Captain", "")).strip()
                        flex_players = [str(row.get(f"Flex{i}", "")).strip() for i in range(1, 6)]
                        captain_id = dk_player_ids.get(captain, {}).get("CPT")
                        flex_ids = [dk_player_ids.get(player, {}).get("FLEX") for player in flex_players]
                        if not captain_id:
                            missing_ids.append(f"{captain} - CPT")
                        for player, player_id in zip(flex_players, flex_ids):
                            if not player_id:
                                missing_ids.append(f"{player} - FLEX")
                        export_rows.append([captain_id or ""] + [player_id or "" for player_id in flex_ids])
                    if missing_ids:
                        st.warning("Some DraftKings CPT/FLEX IDs are missing. Re-upload the correct Showdown template CSV.")
                        st.write(sorted(set(missing_ids)))
                    else:
                        # Keep the official DraftKings entry upload separate from a basic lineup export.
                        showdown_slots = ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]
                        lineup_ids_df = pd.DataFrame(export_rows, columns=showdown_slots)
                        contest_meta = st.session_state.get("selected_dk_contest", {})
                        has_entry_template = (
                            entry_file is not None
                            and selected_contest_id
                            and "entry_df" in locals()
                            and isinstance(entry_df, pd.DataFrame)
                            and not entry_df.empty
                        )
                        if has_entry_template:
                            st.caption("FOR EXISTING ENTRIES: Download this file, then go to DraftKings → My Lineups → Edit Entries → Upload CSV. Do not upload this file on the regular Upload Lineups page. Entry IDs and Contest ID are preserved.")
                            export_df = build_dk_contest_entry_export(
                                entry_df,
                                selected_contest_id,
                                lineup_ids_df,
                                showdown_slots,
                                "Showdown"
                            )
                            if export_df is not None:
                                lineup_export_download(
                                    label="DOWNLOAD FILE FOR EDIT ENTRIES",
                                    data=export_df.to_csv(index=False).encode("utf-8"),
                                    file_name="DraftKings_Showdown_Contest_Entries.csv",
                                    mime="text/csv",
                                    use_container_width=True,
                                    key="dk_showdown_unified_export",
                                    on_click="ignore"
                                )
                                st.caption("On DraftKings, open My Lineups and choose Edit Entries to upload the downloaded replacement CSV.")
                        else:
                            # Always target existing contest entries; don't offer a new-entry upload path.
                            st.warning(
                                "To put these lineups into your existing entries, upload the CSV from DraftKings "
                                "My Contests / Edit Entries in this app and select the matching contest. "
                                "Then this app will make one replacement file that preserves Entry IDs and Contest ID. "
                                "A separate new-lineups export is intentionally disabled."
                            )
            else:
                st.info("Run CONTEST SIM and build your final portfolio first.")

    # Player Pool appears above the SIM handler, so refresh it after a completed
    # Showdown simulation/build to show the newly generated player attributes.
    if build_clicked:
        workspace_rerun(st, _loaded_slate_tabs)


    # ============================================
    # POST-GAME LEARNING
    # ============================================
    with _contest_history:
        with st.expander("Post-Game Learning — Completed Contest CSV", expanded=False):
            st.caption(
                "Upload the completed contest standings CSV. The app compares actual scores, ownership, "
                "CPT/MVP ownership, duplicates, and your finishes with the automatically saved pregame snapshot."
            )
            completed_contest_file = workspace_file_uploader(st,
                "Upload completed contest CSV",
                type=["csv"],
                key="completed_contest_learning_upload",
            )
            learning_username = st.text_input(
                "Your DraftKings/FanDuel entry name",
                value=st.session_state.get("postgame_entry_name", "Meitzlah78"),
                key="postgame_entry_name",
            )

            if completed_contest_file is not None:
                try:
                    completed = pd.read_csv(completed_contest_file, low_memory=False)
                    # Completed-game grading and field learning share the same importer.
                    # Do not attach the currently selected slate's salaries to old games.
                    try:
                        import hashlib as _completed_hash
                        _completed_profiles = ingest_frames([completed], _completed_hash.sha256(completed_contest_file.getvalue()).hexdigest(), platform="Auto", mode="Auto")
                        _completed_store = st.session_state.get("field_history_store", {"schema": 1, "contests": []})
                        _old_profile_ids = {item["id"] for item in _completed_store["contests"]}
                        _new_completed = [item for item in _completed_profiles if item["id"] not in _old_profile_ids]
                        if _new_completed:
                            _completed_store = update_store(_HISTORY_LOCAL, merge_stores(_completed_store, {"schema": 1, "contests": _new_completed}))
                            st.session_state["field_history_store"] = _completed_store
                            st.success("Completed contest added to field learning. Matching future opponent builds will use its anonymous construction profile.")
                    except ValueError as _completed_import_error:
                        st.info("For field learning, import this file through Contest History / Field Learning and select its source format: " + str(_completed_import_error))

                    completed.columns = [str(c).strip() for c in completed.columns]
                    lookup = {str(c).strip().casefold(): c for c in completed.columns}

                    def completed_col(*names):
                        return next((lookup[name.casefold()] for name in names if name.casefold() in lookup), None)

                    rank_col = completed_col("Rank", "Place", "Position")
                    entry_id_col = completed_col("EntryId", "Entry ID")
                    entry_name_col = completed_col("EntryName", "Entry Name")
                    points_col = completed_col("Points", "Score")
                    lineup_col = completed_col("Lineup", "Roster")
                    player_col = completed_col("Player")
                    roster_col = completed_col("Roster Position", "RosterPosition", "Slot")
                    drafted_col = completed_col("%Drafted", "Drafted %", "Ownership %", "Ownership")
                    fpts_col = completed_col("FPTS", "Fantasy Points", "ActualPoints")

                    if rank_col is None or entry_name_col is None:
                        st.error("Completed contest CSV needs Rank and EntryName/Entry Name columns.")
                    else:
                        numeric_rank = pd.to_numeric(completed[rank_col], errors="coerce")
                        entries = completed[numeric_rank.notna()].copy()
                        entries["_Rank"] = pd.to_numeric(entries[rank_col], errors="coerce")
                        if entry_id_col is not None:
                            entries = entries.drop_duplicates(subset=[entry_id_col], keep="first")
                        elif lineup_col is not None:
                            entries = entries.drop_duplicates(subset=[rank_col, entry_name_col, lineup_col], keep="first")

                        field_size = len(entries)
                        duplicate_counts = pd.Series(dtype=int)
                        if lineup_col is not None and not entries.empty:
                            normalized = entries[lineup_col].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
                            duplicate_counts = normalized[normalized.ne("")].value_counts()
                        unique_lineups = int(len(duplicate_counts)) if len(duplicate_counts) else 0
                        average_copies = float(field_size / unique_lineups) if unique_lineups else np.nan
                        max_copies = int(duplicate_counts.max()) if len(duplicate_counts) else 0

                        player_actuals = pd.DataFrame()
                        if player_col is not None and fpts_col is not None:
                            player_rows = completed[[c for c in [player_col, roster_col, drafted_col, fpts_col] if c is not None]].copy()
                            player_rows[player_col] = player_rows[player_col].fillna("").astype(str).str.strip()
                            player_rows["_FPTS"] = pd.to_numeric(player_rows[fpts_col], errors="coerce")
                            player_rows = player_rows[player_rows[player_col].ne("") & player_rows["_FPTS"].notna()].copy()
                            player_actuals = (
                                player_rows.groupby(player_col, as_index=False)["_FPTS"].max()
                                .rename(columns={player_col: "Name", "_FPTS": "ActualPoints"})
                            )
                            if drafted_col is not None:
                                player_rows["_Drafted"] = pd.to_numeric(
                                    player_rows[drafted_col].astype(str).str.replace("%", "", regex=False),
                                    errors="coerce",
                                )
                                if roster_col is not None:
                                    player_rows["_Slot"] = player_rows[roster_col].fillna("").astype(str).str.upper().str.strip()
                                    overall = player_rows.groupby(player_col)["_Drafted"].sum(min_count=1)
                                    special = (
                                        player_rows[player_rows["_Slot"].isin(["CPT", "CAPTAIN", "MVP"])]
                                        .groupby(player_col)["_Drafted"].sum(min_count=1)
                                    )
                                else:
                                    overall = player_rows.groupby(player_col)["_Drafted"].max()
                                    special = pd.Series(dtype=float)
                                player_actuals["Actual Field Own %"] = player_actuals["Name"].map(overall)
                                player_actuals["Actual CPT/MVP Own %"] = player_actuals["Name"].map(special).fillna(0.0)

                        snapshot, snapshot_meta = load_latest_automatic_pregame_snapshot(selected_format)
                        comparison = pd.DataFrame()
                        if isinstance(snapshot, pd.DataFrame) and not snapshot.empty and not player_actuals.empty:
                            snapshot = snapshot.copy()
                            snapshot["Name"] = snapshot["Name"].astype(str).str.strip()
                            comparison = snapshot.merge(player_actuals, on="Name", how="left")
                            comparison["Projection Error"] = (
                                pd.to_numeric(comparison.get("ActualPoints"), errors="coerce")
                                - pd.to_numeric(comparison.get("Projection"), errors="coerce")
                            )
                            percentile_cols = [c for c in ["Sim P10", "Sim P25", "Sim P50", "Sim P75", "Sim P90", "Sim P95", "Sim P99"] if c in comparison.columns]
                            if percentile_cols:
                                def actual_band(row):
                                    actual = pd.to_numeric(row.get("ActualPoints"), errors="coerce")
                                    if pd.isna(actual):
                                        return "No actual score"
                                    ordered = [(10, "Sim P10"), (25, "Sim P25"), (50, "Sim P50"), (75, "Sim P75"), (90, "Sim P90"), (95, "Sim P95"), (99, "Sim P99")]
                                    for pct, col in ordered:
                                        if col in row.index:
                                            value = pd.to_numeric(row.get(col), errors="coerce")
                                            if pd.notna(value) and actual <= value:
                                                return f"At/below P{pct}"
                                    return "Above P99"
                                comparison["Actual vs Sim Range"] = comparison.apply(actual_band, axis=1)

                        username = str(learning_username or "").strip()
                        user_entries = entries[
                            entries[entry_name_col].fillna("").astype(str).str.contains(username, case=False, regex=False)
                        ].copy() if username else pd.DataFrame()
                        actual_winnings = np.nan
                        payout_values = snapshot_meta.get("payout_schedule", []) if isinstance(snapshot_meta, dict) else []
                        if len(user_entries) and payout_values:
                            payout_array = np.asarray(payout_values, dtype=float)
                            ranks = pd.to_numeric(user_entries["_Rank"], errors="coerce").dropna().astype(int)
                            actual_winnings = float(sum(payout_array[rank - 1] for rank in ranks if 1 <= rank <= len(payout_array)))

                        metric_cols = st.columns(4)
                        metric_cols[0].metric("Contest entries", f"{field_size:,}")
                        metric_cols[1].metric("Unique lineups", f"{unique_lineups:,}" if unique_lineups else "N/A")
                        metric_cols[2].metric("Avg copies / lineup", f"{average_copies:.2f}" if pd.notna(average_copies) else "N/A")
                        metric_cols[3].metric("Most-copied lineup", f"{max_copies:,}" if max_copies else "N/A")

                        if len(user_entries):
                            best_rank = int(pd.to_numeric(user_entries["_Rank"], errors="coerce").min())
                            best_score = pd.to_numeric(user_entries[points_col], errors="coerce").max() if points_col else np.nan
                            user_cols = st.columns(4)
                            user_cols[0].metric("Your entries", f"{len(user_entries):,}")
                            user_cols[1].metric("Best rank", f"{best_rank:,}")
                            user_cols[2].metric("Best score", f"{best_score:.2f}" if pd.notna(best_score) else "N/A")
                            user_cols[3].metric("Actual winnings", f"${actual_winnings:,.2f}" if pd.notna(actual_winnings) else "Payout table not saved")

                        if not comparison.empty:
                            scored = comparison.dropna(subset=["ActualPoints", "Projection"], how="any") if "Projection" in comparison.columns else pd.DataFrame()
                            if not scored.empty:
                                mae = float(scored["Projection Error"].abs().mean())
                                bias = float(scored["Projection Error"].mean())
                                acc_cols = st.columns(2)
                                acc_cols[0].metric("Projection MAE", f"{mae:.2f} pts")
                                acc_cols[1].metric("Projection bias", f"{bias:+.2f} pts")
                            st.write("#### Player-by-player learning")
                            show_cols = [c for c in [
                                "Name", "Projection", "ActualPoints", "Projection Error", "Actual vs Sim Range",
                                "Field Own %", "Actual Field Own %", "Field CPT Own %", "Field MVP Own %",
                                "Actual CPT/MVP Own %", "Sim P10", "Sim P50", "Sim P90", "Sim P95", "Sim P99"
                            ] if c in comparison.columns]
                            st.dataframe(injury_frame(st, comparison[show_cols]), use_container_width=True, hide_index=True)

                            output_name = _safe_snapshot_slug(str(snapshot_meta.get("contest_id") or completed_contest_file.name))
                            learning_path = _postgame_learning_dir() / f"{output_name}_learning.csv"
                            comparison.to_csv(learning_path, index=False)
                            st.success("Post-game learning record saved automatically for this app session.")
                        elif player_actuals.empty:
                            st.warning("The standings file loaded, but player FPTS rows were not found, so projection grading is unavailable.")
                        else:
                            st.warning(
                                "No saved pregame snapshot was found for this format. The contest/duplicate results are still shown, "
                                "but projection and ownership comparisons cannot be graded for this game."
                            )
                except Exception as exc:
                    st.error(f"Could not analyze the completed contest CSV: {type(exc).__name__}: {exc}")


        # ============================================
        # SIMMAH ROI TRACKER
        # Tracks real entry fees and winnings. History can be exported and re-imported
        # because Streamlit Cloud session storage may reset between visits.
        with st.expander("SIMMAH ROI Tracker", expanded=False):
            st.caption(
                "Record completed contests using actual entry fees and prize winnings. "
                "Projected contest scores are not counted as real profit."
            )

            ROI_COLUMNS = [
                "Contest Date", "Sport", "Platform / Format", "Contest Name",
                "Entries", "Entry Fee Each ($)", "Total Fees ($)", "Winnings ($)",
                "Net Profit ($)", "ROI (%)", "Best Rank", "Best Score", "Notes"
            ]

            if "roi_history" not in st.session_state:
                st.session_state["roi_history"] = pd.DataFrame(columns=ROI_COLUMNS)

            # Import previously downloaded history when the user chooses to load it.
            roi_upload_col, roi_load_col = st.columns([3, 1])
            with roi_upload_col:
                roi_history_file = workspace_file_uploader(st,
                    "Load saved ROI history CSV",
                    type=["csv"],
                    key="roi_history_file_upload",
                    help="Use this to restore history from a previous SIMMAH session."
                )
            with roi_load_col:
                st.write("")
                st.write("")
                if st.button("LOAD HISTORY", key="roi_load_history_button", use_container_width=True):
                    if roi_history_file is None:
                        st.warning("Choose a saved ROI history CSV first.")
                    else:
                        try:
                            loaded_history = pd.read_csv(roi_history_file)
                            missing_roi_columns = [c for c in ROI_COLUMNS if c not in loaded_history.columns]
                            for column in missing_roi_columns:
                                loaded_history[column] = ""
                            st.session_state["roi_history"] = loaded_history[ROI_COLUMNS].copy()
                            st.success(f"Loaded {len(loaded_history)} contest records.")
                            workspace_rerun(st, _loaded_slate_tabs)
                        except Exception as exc:
                            st.error(f"Could not load that history file: {exc}")

            with st.expander("Record a completed contest", expanded=False):
                with st.form("roi_record_contest_form", clear_on_submit=True):
                    roi_date = st.text_input(
                        "Contest date (YYYY-MM-DD)",
                        value=pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")
                    )
                    roi_sport = st.selectbox(
                        "Sport", ["NFL", "NBA", "WNBA", "MLB", "NHL", "MMA", "NASCAR", "Other"]
                    )
                    roi_format = st.selectbox(
                        "Platform / Format",
                        ["DraftKings Classic", "DraftKings Showdown", "FanDuel Full Roster",
                         "FanDuel Single Game", "Other"]
                    )
                    roi_contest_name = st.text_input("Contest name")
                    roi_entries = st.number_input("Number of entries", min_value=1, value=20, step=1)
                    roi_fee_each = st.number_input(
                        "Entry fee per lineup ($)", min_value=0.0, value=0.10, step=0.10, format="%.2f"
                    )
                    roi_winnings = st.number_input(
                        "Total actual winnings ($)", min_value=0.0, value=0.0, step=0.10, format="%.2f",
                        help="Enter the total prize money DraftKings or FanDuel actually paid for these entries."
                    )
                    roi_best_rank = st.text_input("Best finishing rank (optional)")
                    roi_best_score = st.text_input("Best fantasy score (optional)")
                    roi_notes = st.text_input("Notes (optional)")
                    roi_submit = st.form_submit_button("SAVE CONTEST RESULT", use_container_width=True)

                if roi_submit:
                    try:
                        parsed_roi_date = pd.to_datetime(roi_date, errors="raise").strftime("%Y-%m-%d")
                        entries_value = int(roi_entries)
                        fee_value = round(float(roi_fee_each), 2)
                        winnings_value = round(float(roi_winnings), 2)
                        fees_value = round(entries_value * fee_value, 2)
                        net_value = round(winnings_value - fees_value, 2)
                        roi_value = (net_value / fees_value * 100.0) if fees_value > 0 else 0.0
                        new_roi_row = {
                            "Contest Date": parsed_roi_date,
                            "Sport": roi_sport,
                            "Platform / Format": roi_format,
                            "Contest Name": roi_contest_name.strip(),
                            "Entries": entries_value,
                            "Entry Fee Each ($)": fee_value,
                            "Total Fees ($)": fees_value,
                            "Winnings ($)": winnings_value,
                            "Net Profit ($)": net_value,
                            "ROI (%)": round(roi_value, 2),
                            "Best Rank": roi_best_rank.strip(),
                            "Best Score": roi_best_score.strip(),
                            "Notes": roi_notes.strip(),
                        }
                        existing_roi = st.session_state["roi_history"]
                        st.session_state["roi_history"] = pd.concat(
                            [existing_roi, pd.DataFrame([new_roi_row], columns=ROI_COLUMNS)],
                            ignore_index=True
                        )
                        st.success("Contest result saved to this session.")
                        # Continue into contest scoring on the same run. Restarting the
                        # Streamlit script here can trap the app in a fetch/rerun loop when
                        # DraftKings returns contest details without a complete payout table.
                    except Exception as exc:
                        st.error(f"Could not save this contest result. Check the date and values: {exc}")

            roi_history = st.session_state["roi_history"].copy()
            if not roi_history.empty:
                for numeric_col in ["Total Fees ($)", "Winnings ($)", "Net Profit ($)", "ROI (%)", "Entries"]:
                    roi_history[numeric_col] = pd.to_numeric(roi_history[numeric_col], errors="coerce").fillna(0)
                total_roi_fees = float(roi_history["Total Fees ($)"].sum())
                total_roi_winnings = float(roi_history["Winnings ($)"].sum())
                total_roi_net = total_roi_winnings - total_roi_fees
                total_roi_pct = total_roi_net / total_roi_fees * 100.0 if total_roi_fees > 0 else 0.0
                roi_metrics = st.columns(4)
                roi_metrics[0].metric("Total Entry Fees", f"${total_roi_fees:,.2f}")
                roi_metrics[1].metric("Total Winnings", f"${total_roi_winnings:,.2f}")
                roi_metrics[2].metric("Net Profit / Loss", f"${total_roi_net:,.2f}")
                roi_metrics[3].metric("Overall ROI", f"{total_roi_pct:.1f}%")
                st.dataframe(injury_frame(st, roi_history), use_container_width=True, hide_index=True)
                st.download_button(
                    "DOWNLOAD ROI HISTORY CSV",
                    data=roi_history[ROI_COLUMNS].to_csv(index=False).encode("utf-8"),
                    file_name="SIMMAH_ROI_History.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="roi_download_history_button"
                )
            else:
                st.info("No contest results recorded yet. Enter actual fees and winnings above to start tracking ROI.")





finish_workspaces(st, _loaded_slate_tabs)
