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
    page_title="Universal DFS Simulator",
    page_icon="🏈",
    layout="wide"
)

st.title("Universal DFS Simulator")

# Keep the full projection-update message and refresh button in the fixed top bar.
from datetime import datetime as _sticky_datetime

with st.container(key="sticky_projection_bar"):
    sticky_message, sticky_right = st.columns([3, 2])
    with sticky_message:
        if st.session_state.get("projection_updates_found"):
            st.markdown(
                "**PROJECTION UPDATES FOUND — click REFRESH PROJECTIONS to clear the cache "
                "and reload the latest public projections. Uploaded CSVs still take priority.**"
            )
        else:
            st.markdown("**Uploaded CSVs still take priority.**")
    with sticky_right:
        if st.button("REFRESH PROJECTIONS + INJURY NEWS", key="sticky_refresh_projections", use_container_width=True):
            # Cache functions are defined later in the file, so defer clearing until then.
            st.session_state["pending_sticky_projection_refresh"] = True
            st.rerun()

st.markdown(
    """
    <style>
    .st-key-sticky_projection_bar {
        position: fixed !important;
        top: 3.25rem !important;
        left: 0 !important;
        right: 0 !important;
        z-index: 999999 !important;
        width: 100% !important;
        box-sizing: border-box !important;
        padding: 0.45rem 1rem 0.35rem 1rem;
        background: #000000 !important;
        color: #ffffff !important;
        border: 1px solid #b8a45a;
        border-radius: 0;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
        margin: 0 !important;
    }
    /* Keep the page content clear of the fixed reminder bar. */
    section.main > div.block-container {
        padding-top: 7rem !important;
    }
    .st-key-sticky_projection_bar [data-testid="stHorizontalBlock"] {
        align-items: center;
        gap: 1rem;
    }
    .st-key-sticky_projection_bar p {
        margin-bottom: 0.15rem;
        color: #ffffff !important;
    }
    .st-key-sticky_projection_bar [data-testid="stCaptionContainer"],
    .st-key-sticky_projection_bar [data-testid="stMarkdownContainer"] {
        color: #ffffff !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
top_buttons = st.columns(2)
with top_buttons[0]:
    st.link_button(
        "CONTEST",
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
    if not ownership_df.empty:
        st.write("### " + title)
        st.caption(f"Ownership calculated from {len(field_df):,} simulated opponent lineups. Captain/MVP ownership is shown separately where applicable.")
        st.dataframe(
            ownership_df,
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


def build_showdown_opponent_field(available_players, simulation_df, players_df,
                                  salary_map, captain_salary_map, salary_cap, target,
                                  progress_bar=None, progress_text=None):
    """Build Showdown opponents with cached NumPy arrays to avoid repeated pandas work."""
    columns = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5", "Salary"]
    if target <= 0 or len(available_players) < 6:
        return pd.DataFrame(columns=columns)

    names = np.asarray(list(available_players), dtype=object)
    means = simulation_df.mean(axis=0).reindex(names).fillna(0.01).to_numpy(dtype=float)
    weights = np.clip(means, 0.01, None)
    weights /= weights.sum()
    salaries = np.asarray([int(salary_map.get(name, 0)) for name in names], dtype=np.int64)
    captain_salaries = np.asarray([int(captain_salary_map.get(name, salary_map.get(name, 0))) for name in names], dtype=np.int64)
    team_lookup = players_df.drop_duplicates("Name").set_index("Name")["Team"].to_dict()
    teams = np.asarray([str(team_lookup.get(name, "")) for name in names], dtype=object)
    rng = np.random.default_rng(123)
    rows = []
    attempts = 0
    max_attempts = max(200000, int(target) * 10)

    while len(rows) < target and attempts < max_attempts:
        attempts += 1
        if progress_bar is not None and (attempts % 1000 == 0 or len(rows) >= target):
            progress_bar.progress(
                min(0.99, attempts / max_attempts),
                text=f"Building opponent lineups: {len(rows):,} of {target:,} accepted (attempt {attempts:,})"
            )
        picked = rng.choice(len(names), size=6, replace=False, p=weights)
        # Randomize Captain assignment among the six selected players, weighted by projection.
        # Choosing the highest-projection player every time incorrectly makes the top-projected
        # player Captain in every lineup where they appear, inflating Captain ownership to overall ownership.
        captain_weights = np.clip(means[picked], 0.01, None)
        captain_weights = captain_weights / captain_weights.sum()
        captain_idx = int(rng.choice(picked, p=captain_weights))
        flex_idx = picked[picked != captain_idx]
        salary = int(captain_salaries[captain_idx] + salaries[flex_idx].sum())
        if salary > salary_cap:
            continue
        if len(set(teams[picked])) < 2:
            continue
        rows.append((
            names[captain_idx],
            names[flex_idx[0]], names[flex_idx[1]], names[flex_idx[2]],
            names[flex_idx[3]], names[flex_idx[4]], salary
        ))

    return pd.DataFrame.from_records(rows, columns=columns)


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
    entry_count = len(entries)
    lineup_count = len(lineup_ids_df)
    if lineup_count < entry_count:
        st.warning(
            f"You have {entry_count} entries in this contest but only {lineup_count} lineups. "
            f"Only {lineup_count} existing entries will be updated; build at least {entry_count} lineups to fill them all."
        )
    count = min(entry_count, lineup_count)
    export_df = entries.iloc[:count].copy().reset_index(drop=True)
    ids = lineup_ids_df.iloc[:count].reset_index(drop=True)

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
        "washington": "wsh", "washingtoncommanders": "wsh",
    }
    return aliases.get(raw, raw.upper())


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
        team = normalize_injury_team(team_data.get("abbreviation") or team_data.get("displayName") or team_data.get("name"))
        for injury in team_block.get("injuries", []) or []:
            athlete = injury.get("athlete", {}) or {}
            name = normalize_injury_player_name(athlete.get("fullName") or athlete.get("displayName") or athlete.get("shortName"))
            raw_status = str(injury.get("status") or injury.get("shortComment") or injury.get("detail") or "").strip().casefold()
            if not name or not team or not raw_status:
                continue
            if any(word in raw_status for word in ("injured reserve", "reserve/injured", "physically unable to perform", "out", "suspended")):
                status = "Out"
            elif any(word in raw_status for word in ("doubtful", "questionable", "day-to-day", "probable")):
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

    questionable = result.loc[result["Injury Status"].str.casefold() == "questionable", "Name"].astype(str).tolist()
    excluded = result.loc[result["Injury Status"].str.casefold() == "out", "Name"].astype(str).tolist()
    st.write("### Automatic Injury Statuses")
    st.caption(f"Out: {len(excluded)} | Questionable: {len(questionable)}. Players listed as Out are automatically removed from the player pool.")
    if questionable:
        st.warning("QUESTIONABLE: " + ", ".join(questionable))
    if excluded:
        st.warning("OUT — automatically excluded: " + ", ".join(excluded))
    result = result[result["Injury Status"].str.casefold() != "out"].reset_index(drop=True)
    if result.empty:
        st.error("All players are marked Out. Check the injury feed and player file before continuing.")
        st.stop()
    return result


def exclude_zero_projection_players(frame, slate_label):
    """Remove players with missing, invalid, or zero projections before lineup building."""
    if "Projection" not in frame.columns:
        st.error(f"{slate_label}: projection column is missing, so players cannot be safely ranked.")
        st.stop()
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
        st.stop()
    return result


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
def download_public_projection_table(source_name, platform_name, target_names=None):
    """Download real projections using the same HTML-table/row attributes tested in Colab."""
    import io
    import re
    from html import unescape
    import requests

    target_keys = {
        normalize_projection_player_name(name)
        for name in (target_names or [])
        if normalize_projection_player_name(name)
    }

    def matches_target(projections):
        return not target_keys or bool(target_keys.intersection(projections))

    platform_key = str(platform_name).casefold()
    is_single_game = "single game" in platform_key or "showdown" in platform_key
    site = "fanduel" if "fanduel" in platform_key else "draftkings"

    if source_name == "DFF":
        if is_single_game:
            # This is the working Colab route; DraftKings is the default view.
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
        return {}

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
                dff_table = dff_table.iloc[3:].copy()
                dff_table.columns = [
                    str(col[-1]).strip() if isinstance(col, tuple) else str(col).strip()
                    for col in dff_table.columns
                ]
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
                    if dated_result and matches_target(dated_result):
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
    """Check only the active format every 30 minutes to keep app startup responsive."""
    from datetime import datetime
    status = refresh_public_projection_sources((platform_name,))
    now = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p %Z")
    current_snapshot = st.session_state.get("automatic_projection_snapshot_current", {})
    previous_snapshot = st.session_state.get("automatic_projection_snapshot_previous")
    if previous_snapshot is not None and current_snapshot != previous_snapshot:
        st.session_state["projection_updates_found"] = True
        st.session_state["projection_updates_found_at"] = now
    st.session_state["automatic_projection_snapshot_previous"] = current_snapshot
    st.session_state["automatic_projection_refresh_time"] = now
    st.session_state["automatic_projection_refresh_status"] = status
    successful = [name for name, loaded in status.items() if loaded]
    if st.session_state.get("projection_updates_found"):
        st.warning("PROJECTION UPDATES FOUND — click REFRESH PROJECTIONS to clear the cache and reload the latest public projections. Uploaded CSVs still take priority.")
    if successful:
        st.caption("Automatic projection check: " + ", ".join(successful) + ". Last checked: " + now)
    else:
        st.warning("Automatic projection check could not load any public projection tables. It will try again in 30 minutes.")



def get_projection_source_data(uploaded_file, source_name, platform_name, target_names=None):
    uploaded = read_projection_csv(uploaded_file, source_name)
    if uploaded:
        return uploaded, "uploaded CSV"
    downloaded = download_public_projection_table(source_name, platform_name, target_names=target_names)
    return downloaded, "automatic download" if downloaded else "unavailable"

def apply_external_projection_sources(players_frame, dff_file, draftedge_file, platform_name='DraftKings'):
    """Use only DFF/DraftEdge projections; never substitute internal estimates."""
    result = players_frame.copy()
    target_names = result["Name"].astype(str).tolist() if "Name" in result.columns else []
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    projections, sources = [], []
    dff_matches = draftedge_matches = averages = missing_external = 0

    for _, row in result.iterrows():
        key = normalize_projection_player_name(row.get("Name", ""))
        dff_value, edge_value = dff.get(key), draftedge.get(key)

        if dff_value is not None and edge_value is not None:
            value, source = (dff_value + edge_value) / 2.0, "DFF + DraftEdge average"
            averages += 1
        elif dff_value is not None:
            value, source = dff_value, "DFF"
        elif edge_value is not None:
            value, source = edge_value, "DraftEdge"
        else:
            value, source = np.nan, "No external projection"
            missing_external += 1

        projections.append(value)
        sources.append(source)
        dff_matches += int(dff_value is not None)
        draftedge_matches += int(edge_value is not None)

    result["Projection"] = pd.to_numeric(
        pd.Series(projections, index=result.index), errors="coerce"
    )
    result["ProjectionSource"] = sources
    st.caption(
        f"External projection matches: DFF {dff_matches}; DraftEdge {draftedge_matches}; "
        f"averaged {averages}; missing from both external sources {missing_external}. "
        f"DFF source: {dff_status}; DraftEdge source: {draftedge_status}. "
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


format_options = {
    "DraftKings Classic": ("DraftKings", "Classic"),
    "DraftKings Showdown": ("DraftKings", "Showdown"),
    "FanDuel Full Roster": ("FanDuel", "Full Roster"),
    "FanDuel Single Game": ("FanDuel", "Single Game"),
}
selected_format = st.selectbox(
    "Format",
    list(format_options.keys()),
    key="dfs_format",
)

# Historical projection accuracy report. This uses pre-game projection snapshots
# matched to actual fantasy points; the volatility check below is not a projection backtest.
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
    accuracy_file = st.file_uploader(
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
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)
                    st.write("#### Largest projection misses")
                    misses = accuracy_df.sort_values("Absolute Error", ascending=False).head(20)
                    st.dataframe(
                        misses[[
                            c for c in [
                                "GameDate", "Name", "Position", "ProjectionSource",
                                "Projection", "ActualPoints", "Error", "Absolute Error"
                            ] if c in misses.columns
                        ]].round(2),
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
# Process the sticky refresh request only after both cached functions are defined.
if st.session_state.pop("pending_sticky_projection_refresh", False):
    download_public_projection_table.clear()
    fetch_nfl_injury_statuses.clear()
    st.session_state["projection_updates_found"] = False
    st.session_state["injury_updates_found"] = False
    st.session_state["shared_projection_updated_at"] = _sticky_datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p %Z")
    st.rerun()

platform, lineup_mode = format_options[selected_format]
automatic_projection_refresh(selected_format)
# Keep the derived values in session state for existing format-specific logic.
st.session_state["dfs_platform"] = platform
st.session_state["lineup_mode_" + platform] = lineup_mode
st.subheader(selected_format)

# Initialize from the saved slider value; the control itself appears beside SIM.
aggressiveness = float(st.session_state.get(f"lineup_build_aggressiveness_{platform}_{lineup_mode}", 100 if ((platform == "DraftKings" and lineup_mode == "Showdown") or (platform == "FanDuel" and lineup_mode == "Single Game")) else 50)) / 100.0
P95_WEIGHT = 0.60 - 0.30 * aggressiveness
P99_WEIGHT = 0.10 + 0.45 * aggressiveness
MEAN_WEIGHT = 1.0 - P95_WEIGHT - P99_WEIGHT
STDDEV_WEIGHT = 0.10 * (2.0 * aggressiveness - 1.0)

# The correlation slider is displayed with Build Settings below.
# Read its saved value here; the Build Settings control updates it before SIM runs.
correlation_strength = (
    float(st.session_state.get(f"single_game_correlation_strength_{platform}_{lineup_mode}", 0 if ((platform == "DraftKings" and lineup_mode == "Showdown") or (platform == "FanDuel" and lineup_mode == "Single Game")) else 70)) / 100.0
    if lineup_mode in ("Showdown", "Single Game") else 1.0
)

if platform == "FanDuel":
    # FanDuel uses its own player upload and lineup rules. This separate path
    # keeps DraftKings controls and saved builds unchanged.
    st.write("### Upload FanDuel Salary File")
    st.caption(
        "Upload a FanDuel NFL player CSV. Player names, positions, salaries, "
        "and IDs are read from the file. FanDuel salary-file averages are ignored; "
        "the app uses matching DFF/DraftEdge projections and excludes players "
        "without a valid positive external projection."
    )
    fd_file = st.file_uploader(
        "Upload a FanDuel player CSV",
        type=["csv"],
        key="fd_salary_file"
    )

    st.write("### Contest Selector")
    fd_entry_file = st.file_uploader(
        "Upload FanDuel Contest Entry File",
        type=["csv"],
        key="fd_contest_entry_file",
        help="Upload your FanDuel contest entries CSV. It must include contest name and contest ID columns."
    )
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
            fd_name_col = next((fd_entry_lookup[k] for k in ("contest name", "contest") if k in fd_entry_lookup), None)
            fd_id_col = next((fd_entry_lookup[k] for k in ("contest id", "contestid", "contest_id") if k in fd_entry_lookup), None)
            fd_entries_col = next((fd_entry_lookup[k] for k in ("entry id", "entryid", "entry_id") if k in fd_entry_lookup), None)
            fd_fee_col = next((fd_entry_lookup[k] for k in ("entry fee", "entryfee", "entry_fee", "fee") if k in fd_entry_lookup), None)
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
                st.session_state["selected_fd_contest"] = {
                    "id": str(fd_selected_row[fd_id_col]),
                    "name": str(fd_selected_row[fd_name_col]),
                    "your_entries": int(fd_selected_row["Entries"]),
                    "entry_fee": float(fd_fee) if pd.notna(fd_fee) else None,
                }
                fd_fee_text = f"${float(fd_fee):.2f}" if pd.notna(fd_fee) else "not listed"
                st.success(
                    f"Selected: {fd_selected_row[fd_name_col]} | Contest ID: {fd_selected_row[fd_id_col]} | "
                    f"Your entries: {int(fd_selected_row['Entries'])} | Entry fee: {fd_fee_text}"
                )
                st.caption(
                    "The entry file identifies your contest and entries. Opponent lineups and payouts are simulated, not taken from actual contest results."
                )
        except Exception as exc:
            st.error(f"Could not read the FanDuel contest entry file: {exc}")

    fd_opponent_target = get_contest_opponent_target("fd")
    st.caption(f"Simulated FanDuel opponents: up to {fd_opponent_target:,} (speed limit)")

    st.write("### Projection Sources")
    fd_dff_projection_file = None
    fd_draftedge_projection_file = None
    show_projection_refresh_status(
        [("DFF", fd_dff_projection_file), ("DraftEdge", fd_draftedge_projection_file)],
        "fd_" + lineup_mode.replace(" ", "_").lower()
    )

    if fd_file is None:
        st.info("Upload your FanDuel salary CSV to build FanDuel lineups.")
        st.stop()

    try:
        # FanDuel exports may include preamble rows or inconsistent rows before
        # the actual player table. Find the real header row before parsing.
        import csv
        import io

        fd_text = fd_file.getvalue().decode("utf-8-sig", errors="replace")
        fd_lines = fd_text.splitlines()
        fd_header_line = None
        for line_index, line in enumerate(fd_lines[:60]):
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
            st.stop()

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
        fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
        fd_players["Opponent"] = fd_players["Team"].map(fd_opponents).fillna("—")
        fd_players["Position"] = fd_raw[fd_pos_col].astype(str).str.strip().str.upper()
        # Do not invent projections from salary. The external-source loader below
        # fills this column with DFF/DraftEdge values or NaN if neither source matches.
        fd_players["Projection"] = np.nan
        if fd_id_col is not None:
            fd_players["FD_ID"] = fd_raw[fd_id_col].astype(str).str.strip()

        fd_players = fd_players.dropna(subset=["Salary"])
        fd_players = fd_players[
            (fd_players["Name"] != "") &
            (fd_players["Name"].str.lower() != "nan") &
            (fd_players["Salary"] > 0)
        ].drop_duplicates(subset=["Name"], keep="first").reset_index(drop=True)

        if fd_players.empty:
            st.error("No usable players were found in that CSV.")
            st.stop()

    except Exception as exc:
        st.error(f"Could not read that FanDuel CSV: {exc}")
        st.stop()

    fd_players = apply_external_projection_sources(fd_players, fd_dff_projection_file, fd_draftedge_projection_file, platform_name=("FanDuel Single Game" if lineup_mode == "Single Game" else "FanDuel Full Roster"))
    fd_players = exclude_zero_projection_players(fd_players, "FanDuel " + lineup_mode)
    fd_players = apply_injury_statuses(fd_players, "injury_status_fd_" + lineup_mode.replace(" ", "_").lower())

    # Restore FanDuel's saved simulation summaries on every Streamlit rerun.
    fd_sim_key = "fd_player_sim_" + lineup_mode.replace(" ", "_").lower()
    player_sim = st.session_state.get(fd_sim_key, {})
    if not isinstance(player_sim, dict):
        player_sim = {}
    for _, fd_row in fd_players.iterrows():
        fd_name = str(fd_row["Name"])
        if fd_name not in player_sim:
            fd_projection = max(float(fd_row.get("Projection", 0.01) or 0.01), 0.01)
            player_sim[fd_name] = {
                "Mean": fd_projection,
                "P10": fd_projection * 0.35,
                "P25": fd_projection * 0.65,
                "P50": fd_projection,
                "P75": fd_projection * 1.25,
                "P90": fd_projection * 1.65,
                "P95": fd_projection * 1.8,
                "P99": fd_projection * 2.3,
                "StdDev": 0.0,
            }
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

    st.caption("The 5,000-lineup build automatically spreads player exposure while still favoring stronger simulated scores.")
    build_cols = st.columns([1, 1, 0.65])
    with build_cols[0]:
        st.write("### Build Settings")
        fd_salary_range = st.slider(
            "Allowed lineup salary range",
            min_value=0,
            max_value=60000,
            value=(54000, 60000),
            step=100,
            format="$%d",
            key="fd_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),
            help="Only build lineups whose total salary falls inside this range."
        )
    with build_cols[1]:
        aggressiveness_pct = st.slider(
            "Lineup Build Aggressiveness", 0, 100,
            100 if ((platform == "DraftKings" and lineup_mode == "Showdown") or (platform == "FanDuel" and lineup_mode == "Single Game")) else 50,
            step=5,
            help="Conservative favors steadier outcomes; aggressive favors ceiling and volatility. Does not change simulation or lineup counts.",
            key=f"lineup_build_aggressiveness_{platform}_{lineup_mode}",
        )
        aggressiveness = aggressiveness_pct / 100.0
        P95_WEIGHT = 0.60 - 0.30 * aggressiveness
        P99_WEIGHT = 0.10 + 0.45 * aggressiveness
        MEAN_WEIGHT = 1.0 - P95_WEIGHT - P99_WEIGHT
        STDDEV_WEIGHT = 0.10 * (2.0 * aggressiveness - 1.0)
        st.caption(f"Build style: {aggressiveness_pct}% aggressive · P95 {P95_WEIGHT:.0%} · P99 {P99_WEIGHT:.0%} · average {MEAN_WEIGHT:.0%} · volatility {STDDEV_WEIGHT:+.0%}.")
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
        fd_run_all_clicked = st.button(
            "RUN SIM → BUILD → CONTEST SIM",
            type="primary",
            use_container_width=True,
            key="fd_run_all_" + lineup_mode.replace(" ", "_").lower(),
            help="Run all three FanDuel steps in order, with a progress bar."
        )
        fd_sim_clicked = fd_run_all_clicked
        fd_build_clicked = fd_run_all_clicked
        fd_contest_clicked = fd_run_all_clicked
        fd_progress_bar = None
        if fd_run_all_clicked:
            fd_progress_bar = st.progress(2, text="Starting FanDuel simulation...")
        if fd_sim_clicked:
            with st.spinner(f"Running {SIMULATION_COUNT:,} FanDuel scoring simulations..."):
                rng = np.random.default_rng()
                position_rates = {
                    "QB": 2.00, "RB": 1.75, "WR": 1.70, "TE": 1.50,
                    "K": 1.35, "D": 1.35, "DST": 1.35, "DEF": 1.35
                }
                # FanDuel scoring differs from DraftKings: half-point receptions,
                # -2 lost fumbles, and no 300/100-yard bonuses.
                simulated_scores = np.zeros((SIMULATION_COUNT, len(fd_players)), dtype=float)
                for index, (_, player_row) in enumerate(fd_players.iterrows()):
                    if fd_run_all_clicked:
                        sim_pct = 3 + int(25 * (index / max(1, len(fd_players))))
                        fd_progress_bar.progress(
                            sim_pct,
                            text=f"Simulating FanDuel players: {index + 1:,} of {len(fd_players):,}..."
                        )
                    positions = set(str(player_row["Position"]).upper().replace(" ", "").split("/"))
                    n = SIMULATION_COUNT
                    if "QB" in positions:
                        stats = {"passing_yards": np.maximum(0, rng.normal(225, 65, n)),
                                 "passing_tds": rng.poisson(1.45, n), "interceptions": rng.poisson(0.65, n),
                                 "rushing_yards": np.maximum(0, rng.normal(16, 20, n)),
                                 "rushing_tds": rng.binomial(1, 0.12, n)}
                    elif "RB" in positions:
                        stats = {"rushing_yards": np.maximum(0, rng.normal(55, 30, n)),
                                 "rushing_tds": rng.binomial(2, 0.18, n),
                                 "receiving_yards": np.maximum(0, rng.normal(22, 20, n)),
                                 "receiving_tds": rng.binomial(1, 0.10, n), "receptions": rng.poisson(2.5, n)}
                    elif "WR" in positions:
                        stats = {"receiving_yards": np.maximum(0, rng.normal(55, 35, n)),
                                 "receiving_tds": rng.binomial(1, 0.28, n), "receptions": rng.poisson(4.0, n),
                                 "rushing_yards": np.maximum(0, rng.normal(2, 5, n))}
                    elif "TE" in positions:
                        stats = {"receiving_yards": np.maximum(0, rng.normal(34, 24, n)),
                                 "receiving_tds": rng.binomial(1, 0.20, n), "receptions": rng.poisson(2.7, n)}
                    elif positions & {"K"}:
                        stats = {"fg_under_40": rng.poisson(1.0, n), "fg_40_49": rng.poisson(0.5, n),
                                 "fg_50_plus": rng.poisson(0.25, n), "extra_points_made": rng.poisson(2.0, n)}
                    else:
                        stats = {"sacks": rng.poisson(2.3, n), "def_interceptions": rng.binomial(1, 0.7, n),
                                 "fumble_recoveries": rng.binomial(1, 0.45, n), "defensive_tds": rng.binomial(1, 0.08, n),
                                 "safeties": rng.binomial(1, 0.03, n), "blocked_kicks": rng.binomial(1, 0.04, n),
                                 "points_allowed": np.clip(rng.normal(22, 10, n), 0, 50),
                                 "yards_allowed": np.clip(rng.normal(350, 80, n), 0, 650), "is_defense": 1}
                    score = (
                        np.asarray(stats.get("passing_yards", 0), dtype=float) * 0.04
                        + np.asarray(stats.get("passing_tds", 0), dtype=float) * 4
                        - np.asarray(stats.get("interceptions", 0), dtype=float)
                        + np.asarray(stats.get("rushing_yards", 0), dtype=float) * 0.1
                        + np.asarray(stats.get("rushing_tds", 0), dtype=float) * 6
                        + np.asarray(stats.get("receiving_yards", 0), dtype=float) * 0.1
                        + np.asarray(stats.get("receiving_tds", 0), dtype=float) * 6
                        + np.asarray(stats.get("receptions", 0), dtype=float) * 0.5
                        - np.asarray(stats.get("fumbles_lost", 0), dtype=float) * 2
                        + np.asarray(stats.get("fg_under_40", 0), dtype=float) * 3
                        + np.asarray(stats.get("fg_40_49", 0), dtype=float) * 4
                        + np.asarray(stats.get("fg_50_plus", 0), dtype=float) * 5
                        + np.asarray(stats.get("extra_points_made", 0), dtype=float)
                        + np.asarray(stats.get("sacks", 0), dtype=float)
                        + np.asarray(stats.get("def_interceptions", 0), dtype=float) * 2
                        + np.asarray(stats.get("fumble_recoveries", 0), dtype=float) * 2
                        + np.asarray(stats.get("defensive_tds", 0), dtype=float) * 6
                        + np.asarray(stats.get("safeties", 0), dtype=float) * 2
                        + np.asarray(stats.get("blocked_kicks", 0), dtype=float) * 2
                    )
                    if "D" in positions or "DST" in positions or "DEF" in positions:
                        pa = np.asarray(stats["points_allowed"], dtype=float)
                        ya = np.asarray(stats["yards_allowed"], dtype=float)
                        score += np.select([pa == 0, pa <= 6, pa <= 13, pa <= 20, pa <= 27, pa <= 34],
                                           [10, 7, 4, 1, 0, -1], default=-4)
                        score += np.select([ya <= 100, ya <= 199, ya <= 299, ya <= 349, ya <= 399, ya <= 449, ya <= 499],
                                           [3, 2, 1, 0, -1, -3, -5], default=-7)
                    # Use each player's projection as the center of the outcomes,
                    # while retaining the position-specific shape and volatility.
                    # This prevents every QB/WR/etc. from receiving nearly the same
                    # distribution just because they share a position.
                    raw_scores = np.asarray(score, dtype=float)
                    raw_mean = float(np.mean(raw_scores))
                    raw_std = float(np.std(raw_scores))
                    target_mean = float(pd.to_numeric(
                        pd.Series([player_row.get("Projection", 0.01)]),
                        errors="coerce"
                    ).fillna(0.01).iloc[0])
                    cv_by_position = {
                        "QB": 0.35, "RB": 0.45, "WR": 0.55, "TE": 0.60,
                        "K": 0.45, "D": 0.65, "DST": 0.65, "DEF": 0.65
                    }
                    main_position = next(
                        (p for p in ("QB", "RB", "WR", "TE", "K", "D", "DST", "DEF") if p in positions),
                        "WR"
                    )
                    target_std = max(1.5, abs(target_mean) * cv_by_position[main_position])
                    if raw_std > 1e-8:
                        adjusted_scores = (raw_scores - raw_mean) * (target_std / raw_std) + target_mean
                    else:
                        adjusted_scores = np.full(n, target_mean, dtype=float)
                    simulated_scores[:, index] = adjusted_scores

                # FanDuel's build stage uses the same distribution summaries as DraftKings.
                # Keep them in this branch because FanDuel's UI exits before the shared DK engine.
                player_sim = {}
                for sim_index, sim_name in enumerate(fd_players["Name"].astype(str)):
                    values = simulated_scores[:, sim_index]
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
                st.session_state["fd_player_sim_" + lineup_mode.replace(" ", "_").lower()] = player_sim
                st.session_state["fd_simulation_ready_" + lineup_mode.replace(" ", "_").lower()] = True
            if fd_run_all_clicked:
                fd_progress_bar.progress(30, text="Simulation complete. Building 5,000 FanDuel lineups...")

        st.success(f"Loaded {len(fd_players)} FanDuel players after injury-status filtering.")
        if fd_proj_col is None:
            st.caption(
                "FanDuel salary-file averages are ignored. Check ProjectionSource "
                "in the player table to see whether DFF or DraftEdge matched. "
                "Players without a valid positive external projection are excluded."
            )
        fd_player_display = fd_players.drop(columns=["FD_ID"], errors="ignore").copy()
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

        st.dataframe(
            fd_player_display,
            use_container_width=True,
            hide_index=True,
            column_config={"Name": st.column_config.TextColumn("Name", pinned=True)},
        )
        with st.expander("Copy Player Info to ChatGPT"):
            st.caption("Click inside the text box, press Ctrl+A, then Ctrl+C. Paste the copied text into ChatGPT.")
            fd_copy_text = fd_player_display.to_csv(index=False, sep="\t", na_rep="")
            st.text_area(
                "Player data (copy this text)",
                value=fd_copy_text,
                height=300,
                key="fd_chatgpt_player_export",
                label_visibility="collapsed"
            )

        fd_signature = (
            "FanDuel",
            lineup_mode,
            tuple(fd_players[["Name", "Position", "Team", "Salary", "Projection"]]
                  .astype(str).itertuples(index=False, name=None))
        )
        if "fd_saved_builds" not in st.session_state:
            st.session_state["fd_saved_builds"] = {}
        fd_build_key = "fd_lineups_" + lineup_mode.replace(" ", "_").lower()
        fd_active_key = "fd_active_signature_" + lineup_mode.replace(" ", "_").lower()
        previous_fd_signature = st.session_state.get(fd_active_key)
        if previous_fd_signature != fd_signature:
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

        if fd_build_clicked:
            # A new run must replace this mode's previous build, not leave stale
            # lineups visible if the current build cannot produce valid results.
            st.session_state.pop(fd_build_key, None)
            st.session_state.pop("fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower(), None)
            st.session_state.pop("fd_contest_field_" + lineup_mode.replace(" ", "_").lower(), None)
            st.session_state.pop("fd_contest_field_ready_" + lineup_mode.replace(" ", "_").lower(), None)
            rng = np.random.default_rng()
            pool = fd_players.copy()
            pool["Eligible"] = pool["Position"].apply(
                lambda value: set(str(value).upper().replace(" ", "").split("/"))
            )
            pool = pool.drop_duplicates("Name", keep="first").reset_index(drop=True)
            names = pool["Name"].astype(str).to_numpy(dtype=object)
            salaries = pd.to_numeric(pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
            projections = pd.to_numeric(pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01).to_numpy(dtype=float)
            sim_means = np.asarray([float(player_sim.get(name, {}).get("Mean", projections[i])) for i, name in enumerate(names)], dtype=float)
            lineup_scores = np.asarray([
                float(player_sim.get(name, {}).get("P95", projections[i])) * P95_WEIGHT
                + float(player_sim.get(name, {}).get("P99", projections[i] * 2.3)) * P99_WEIGHT
                + sim_means[i] * MEAN_WEIGHT
                + float(player_sim.get(name, {}).get("StdDev", 0.0)) * STDDEV_WEIGHT
                for i, name in enumerate(names)
            ], dtype=float)
            lineup_scores, fd_ownership_proxy = ownership_adjusted_player_scores(
                pool, names, np.clip(lineup_scores, 0.01, None), player_sim
            )
            eligible_sets = pool["Eligible"].tolist()
            results = []
            seen = set()
            player_build_counts = {str(name): 0 for name in names}
            target_lineups = 2000
            max_attempts = 500000
            salary_min, salary_max = int(fd_salary_range[0]), min(int(fd_salary_range[1]), 60000)
            if lineup_mode == "Single Game":
                slots = ["MVP", "FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5"]
                mvp_indices = np.flatnonzero((salaries * 1.5 <= salary_max))
                mvp_weights = lineup_scores[mvp_indices].copy()
                if len(mvp_weights):
                    mvp_weights /= mvp_weights.sum()
            else:
                roster = [
                    ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                    ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                    ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}),
                    ("D", {"D", "DST", "DEF"})
                ]
                slots = [slot for slot, _ in roster]
                eligible_indices = {
                    slot: np.asarray([i for i, positions in enumerate(eligible_sets) if positions & eligible], dtype=int)
                    for slot, eligible in roster
                }

            for build_attempt in range(max_attempts):
                if fd_run_all_clicked and (build_attempt % 1000 == 0):
                    build_progress = min(
                        59,
                        30 + int(29 * max(
                            len(results) / max(target_lineups, 1),
                            build_attempt / max_attempts
                        ))
                    )
                    fd_progress_bar.progress(
                        build_progress,
                        text=f"Building FanDuel lineups: {len(results):,} of {target_lineups:,} accepted (attempt {build_attempt:,} of {max_attempts:,})..."
                    )
                chosen_indices = []
                chosen = {}
                used = set()
                salary = 0
                total_points = 0.0
                total_score = 0.0
                if lineup_mode == "Single Game":
                    if not len(mvp_indices):
                        break
                    mvp_idx = int(rng.choice(mvp_indices, p=mvp_weights))
                    chosen["MVP"] = names[mvp_idx]
                    chosen_indices.append(mvp_idx)
                    used.add(mvp_idx)
                    salary = int(round(salaries[mvp_idx] * 1.5))
                    total_points = sim_means[mvp_idx] * 1.5
                    total_score = lineup_scores[mvp_idx] * 1.5
                    for slot in slots[1:]:
                        choices = np.asarray([
                            i for i in range(len(names))
                            if i not in used and salary + salaries[i] <= salary_max
                        ], dtype=int)
                        if not len(choices):
                            break
                        weights = lineup_scores[choices].copy()
                        expected_exposure = max(1.0, target_lineups * len(slots) / max(1, len(names)))
                        exposure_penalty = np.asarray([
                            (1.0 + player_build_counts.get(str(names[i]), 0) / expected_exposure) ** 1.5
                            for i in choices
                        ], dtype=float)
                        weights /= exposure_penalty
                        weights /= weights.sum()
                        picked = int(rng.choice(choices, p=weights))
                        chosen[slot] = names[picked]
                        chosen_indices.append(picked)
                        used.add(picked)
                        salary += int(salaries[picked])
                        total_points += sim_means[picked]
                        total_score += lineup_scores[picked]
                else:
                    for slot, _ in roster:
                        choices = np.asarray([
                            i for i in eligible_indices[slot]
                            if i not in used and salary + salaries[i] <= salary_max
                        ], dtype=int)
                        if not len(choices):
                            break
                        weights = lineup_scores[choices].copy()
                        expected_exposure = max(1.0, target_lineups * len(slots) / max(1, len(names)))
                        exposure_penalty = np.asarray([
                            (1.0 + player_build_counts.get(str(names[i]), 0) / expected_exposure) ** 1.5
                            for i in choices
                        ], dtype=float)
                        weights /= exposure_penalty
                        weights /= weights.sum()
                        picked = int(rng.choice(choices, p=weights))
                        chosen[slot] = names[picked]
                        chosen_indices.append(picked)
                        used.add(picked)
                        salary += int(salaries[picked])
                        total_points += sim_means[picked]
                        total_score += lineup_scores[picked]
                if len(chosen) != len(slots) or salary < salary_min or salary > salary_max:
                    continue
                lineup_key = tuple(chosen[slot] for slot in slots)
                if lineup_key in seen:
                    continue
                seen.add(lineup_key)
                for player_name in set(chosen.values()):
                    player_build_counts[str(player_name)] = player_build_counts.get(str(player_name), 0) + 1
                results.append({**chosen, "Salary": salary, "ProjectedPoints": round(total_points, 2), "Score": round(total_score, 2)})
                if len(results) >= target_lineups:
                    break

            if results:
                fd_results = pd.DataFrame(results).sort_values(
                    "Score", ascending=False
                ).reset_index(drop=True)
                st.session_state[fd_build_key] = fd_results
                st.session_state["fd_saved_builds"][fd_signature] = {"lineups": fd_results}
            else:
                st.error(
                    "No valid lineups found. Check player positions, salary values, "
                    "and make sure the uploaded slate has enough players for this contest type."
                )
            if fd_run_all_clicked:
                fd_progress_bar.progress(
                    60,
                    text="Lineup build complete. Simulating the contest field..."
                    if results else "Lineup build did not produce valid lineups."
                )

        if fd_contest_clicked:
            fd_pool = fd_players.copy()
            fd_pool["Eligible"] = fd_pool["Position"].apply(
                lambda value: set(str(value).upper().replace(" ", "").split("/"))
            )
            # This is already the filtered FanDuel pool. Never apply a shared
            # DraftKings available_players list to FanDuel contest opponents.
            fd_pool["Projection"] = pd.to_numeric(fd_pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01)
            fd_weights = fd_pool["Projection"].to_numpy(dtype=float)
            fd_weights = fd_weights / fd_weights.sum() if fd_weights.sum() else np.full(len(fd_pool), 1 / max(len(fd_pool), 1))
            rng = np.random.default_rng(123)
            opponent_rows = []
            seen_opponents = set()
            attempts = 0
            if len(fd_pool) < len(fd_slots):
                st.error(f"At least {len(fd_slots)} eligible players are required for FanDuel Contest Sim.")
            else:
                if fd_opponent_target <= 0:
                    st.warning("Total contest entries must be greater than your own entries.")
                with st.spinner(f"Building {fd_opponent_target:,} simulated FanDuel contest entries..."):
                    while len(opponent_rows) < fd_opponent_target and attempts < max(300000, fd_opponent_target * 15):
                        attempts += 1
                        if attempts % 1000 == 0 and fd_opponent_target > 0:
                            max_field_attempts = max(300000, fd_opponent_target * 15)
                            field_progress = max(
                                len(opponent_rows) / max(fd_opponent_target, 1),
                                attempts / max_field_attempts
                            )
                            progress_pct = 60 + int(35 * min(field_progress, 1.0))
                            fd_progress_bar.progress(
                                min(progress_pct, 95),
                                text=(
                                    f"Simulating contest field: {len(opponent_rows):,} of "
                                    f"{fd_opponent_target:,} opponents (attempt {attempts:,})..."
                                )
                            )
                        chosen = {}
                        used = set()
                        salary = 0
                        points = 0.0
                        if lineup_mode == "Single Game":
                            mvp_candidates = fd_pool[
                                (fd_pool["Salary"] * 1.5 <= fd_salary_range[1])
                                & (fd_pool["Salary"] * 1.5 <= 60000)
                            ]
                            if mvp_candidates.empty:
                                break
                            mvp_weights = mvp_candidates["Projection"].to_numpy(dtype=float)
                            mvp_weights = mvp_weights / mvp_weights.sum()
                            mvp_row = mvp_candidates.iloc[int(rng.choice(len(mvp_candidates), p=mvp_weights))]
                            mvp = str(mvp_row["Name"])
                            chosen["MVP"] = mvp
                            used.add(mvp)
                            salary = int(float(mvp_row["Salary"]) * 1.5)
                            points = float(mvp_row["Projection"]) * 1.5
                            for slot in ["FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5"]:
                                choices = fd_pool[
                                    (~fd_pool["Name"].isin(used))
                                    & ((fd_pool["Salary"] + salary) <= fd_salary_range[1])
                                    & ((fd_pool["Salary"] + salary) <= 60000)
                                ]
                                if choices.empty:
                                    break
                                weights = choices["Projection"].to_numpy(dtype=float)
                                weights = weights / weights.sum()
                                picked = choices.iloc[int(rng.choice(len(choices), p=weights))]
                                name = str(picked["Name"])
                                chosen[slot] = name
                                used.add(name)
                                salary += int(picked["Salary"])
                                points += float(picked["Projection"])
                        else:
                            roster = [
                                ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                                ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                                ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}),
                                ("D", {"D", "DST", "DEF"})
                            ]
                            for slot, eligible in roster:
                                choices = fd_pool[
                                    (~fd_pool["Name"].isin(used))
                                    & fd_pool["Eligible"].apply(lambda positions: bool(positions & eligible))
                                    & ((fd_pool["Salary"] + salary) <= fd_salary_range[1])
                                    & ((fd_pool["Salary"] + salary) <= 60000)
                                ]
                                if choices.empty:
                                    break
                                weights = choices["Projection"].to_numpy(dtype=float)
                                weights = weights / weights.sum()
                                picked = choices.iloc[int(rng.choice(len(choices), p=weights))]
                                name = str(picked["Name"])
                                chosen[slot] = name
                                used.add(name)
                                salary += int(picked["Salary"])
                                points += float(picked["Projection"])
                        if len(chosen) != len(fd_slots):
                            continue
                        if salary < fd_salary_range[0] or salary > fd_salary_range[1] or salary > 60000:
                            continue
                        key = tuple(chosen[slot] for slot in fd_slots)
                        if key in seen_opponents:
                            continue
                        seen_opponents.add(key)
                        opponent_rows.append({**chosen, "Salary": salary, "ProjectedPoints": round(points, 2)})
                opponent_df = pd.DataFrame(opponent_rows)
                st.session_state["fd_contest_field_" + lineup_mode.replace(" ", "_").lower()] = opponent_df
                st.session_state["fd_contest_field_ready_" + lineup_mode.replace(" ", "_").lower()] = not opponent_df.empty
                if not opponent_df.empty:
                    show_field_ownership(opponent_df, fd_slots, "Simulated FanDuel Player Ownership", captain_slot=("MVP" if lineup_mode == "Single Game" else None))
                    st.success(f"Created {len(opponent_df):,} simulated FanDuel opponent lineups.")
                    fd_contest_details = st.session_state.get("selected_fd_contest")
                    if fd_contest_details:
                        st.info(
                            f"Contest selected from your FanDuel entry CSV: {fd_contest_details['name']} "
                            f"(ID {fd_contest_details['id']}). Your file has "
                            f"{fd_contest_details['your_entries']} entries in this contest. "
                            "The opponent field is simulated."
                        )
                    user_lineups = st.session_state.get(fd_build_key)
                    if user_lineups is None or user_lineups.empty:
                        st.warning("SIM is running the lineup build and contest comparison together.")
                    else:
                        scores = opponent_df["ProjectedPoints"].to_numpy(dtype=float)
                        compared = add_lineup_field_ownership(user_lineups.copy())
                        compared["BeatsOpponents"] = compared["ProjectedPoints"].apply(lambda score: int(np.sum(scores < float(score))))
                        compared["FieldPercentile"] = compared["ProjectedPoints"].apply(lambda score: round(100.0 * np.mean(scores <= float(score)), 1))
                        compared["FieldRank"] = compared["ProjectedPoints"].apply(lambda score: 1 + int(np.sum(scores > float(score))))
                        compared = add_field_ranking_metrics(compared, scores)
                        st.session_state["fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()] = compared
                        st.write("### FanDuel Lineups vs. Simulated Contest Field")
                        st.caption("This is an estimate using projected points, not actual contest results.")
                        st.dataframe(compared, use_container_width=True, hide_index=True)
                        # Keep the contest results area consistent with DraftKings Classic and Showdown.
                else:
                    st.error("Could not create valid FanDuel opponent lineups. Check the player pool and salary range.")
            if fd_run_all_clicked:
                fd_progress_bar.progress(
                    100,
                    text="FanDuel SIM → BUILD → CONTEST SIM finished."
                )

        fd_results = st.session_state.get(fd_build_key)
        if fd_results is not None:
            fd_results = remove_out_players_from_lineups(fd_results, fd_slots, "FanDuel")
            st.session_state[fd_build_key] = fd_results
            st.write(f"Built {len(fd_results)} FanDuel lineups.")

            # Use the same ranking choices as DraftKings Showdown for both FanDuel formats.
            fd_comparison_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()
            fd_rank_source = st.session_state.get(fd_comparison_key)
            if not isinstance(fd_rank_source, pd.DataFrame) or fd_rank_source.empty:
                fd_rank_source = add_field_ranking_metrics(fd_results, fd_results["ProjectedPoints"].to_numpy(dtype=float))
            fd_rank_label = st.selectbox(
                "Rank lineups by", list(PORTFOLIO_METRICS.keys()),
                key="fd_rank_metric_" + lineup_mode.replace(" ", "_").lower()
            )
            fd_rank_column = PORTFOLIO_METRICS[fd_rank_label]
            fd_rank_source = fd_rank_source.sort_values(fd_rank_column, ascending=False).reset_index(drop=True)
            fd_rank_count = st.number_input(
                "Number of lineups to show", min_value=1, max_value=max(1, len(fd_rank_source)),
                value=min(20, max(1, len(fd_rank_source))), step=1,
                key="fd_rank_count_" + lineup_mode.replace(" ", "_").lower()
            )
            st.caption("Run SIM/contest comparison first for field-based estimates. Without a completed comparison, ranking uses the available lineup results as a temporary estimate.")
            # Keep all built lineups for export. The display limit only controls
            # how many rows are shown on screen, not how many get downloaded.
            fd_all_ranked = fd_rank_source.copy()
            fd_results = fd_all_ranked.head(int(fd_rank_count)).copy()

            # Use the same player-by-player points layout as the DraftKings Portfolio.
            fd_display = fd_results.copy()
            fd_player_means = {
                str(name): float(values.get("Mean", 0.0))
                for name, values in player_sim.items()
            }
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
            fd_display_columns = list(dict.fromkeys(
                col for col in fd_display_columns if col in fd_display.columns
            ))
            st.dataframe(
                fd_display[fd_display_columns] if fd_display_columns else fd_display,
                use_container_width=True,
                hide_index=True
            )

            if "FD_ID" in fd_players.columns:
                fd_ids = dict(zip(fd_players["Name"], fd_players["FD_ID"].astype(str)))
                export_slots = (
                    ["MVP", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]
                    if lineup_mode == "Single Game"
                    else ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "D"]
                )
                export_data = []
                missing_ids = []
                for _, lineup in fd_all_ranked.iterrows():
                    row_ids = []
                    for slot in fd_slots:
                        name = lineup[slot]
                        player_id = fd_ids.get(name, "")
                        if not player_id or player_id.lower() == "nan":
                            missing_ids.append(name)
                        row_ids.append(player_id)
                    export_data.append(row_ids)
                if missing_ids:
                    st.warning("Some player IDs are missing, so export is unavailable.")
                else:
                    export_df = pd.DataFrame(export_data, columns=export_slots)
                    selected_fd_contest = st.session_state.get("selected_fd_contest")
                    if fd_entry_file is None or not selected_fd_contest:
                        st.warning(
                            "Upload your FanDuel contest entry template and select the contest above "
                            "to create a replacement CSV. A lineup-only CSV cannot replace existing entries."
                        )
                    else:
                        try:
                            import csv
                            import io
                            fd_template_text = fd_entry_file.getvalue().decode("utf-8-sig", errors="replace")
                            fd_template_rows = list(csv.reader(io.StringIO(fd_template_text)))
                            if not fd_template_rows:
                                raise ValueError("The uploaded FanDuel entry template is empty.")
                            fd_template_header = [str(c).strip() for c in fd_template_rows[0]]
                            fd_entry_end = 1
                            while fd_entry_end < len(fd_template_rows):
                                row = fd_template_rows[fd_entry_end]
                                if not row or not str(row[0]).strip():
                                    break
                                fd_entry_end += 1

                            header_lookup = {}
                            for i, column in enumerate(fd_template_header):
                                key_name = str(column).strip().upper()
                                header_lookup.setdefault(key_name, []).append(i)
                            if lineup_mode == "Single Game":
                                slot_aliases = [
                                    ("MVP", {"MVP", "MVP - 1.5X POINTS"}),
                                    ("FLEX1", {"ANYFLEX", "FLEX"}),
                                    ("FLEX2", {"ANYFLEX", "FLEX"}),
                                    ("FLEX3", {"ANYFLEX", "FLEX"}),
                                    ("FLEX4", {"ANYFLEX", "FLEX"}),
                                    ("FLEX5", {"ANYFLEX", "FLEX"}),
                                ]
                            else:
                                slot_aliases = [
                                    ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                                    ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                                    ("TE", {"TE"}), ("FLEX", {"FLEX"}), ("D", {"D", "DEF", "DST"}),
                                ]
                            roster_column_indices = []
                            used_indices = set()
                            for slot_name, aliases in slot_aliases:
                                index = next(
                                    (i for alias in aliases for i in header_lookup.get(alias, [])
                                     if i not in used_indices),
                                    None
                                )
                                if index is None:
                                    raise ValueError(
                                        f"Could not find the FanDuel upload column for {slot_name}. "
                                        "Make sure you uploaded the correct Single Game or Full Roster template."
                                    )
                                roster_column_indices.append(index)
                                used_indices.add(index)

                            entry_id_index = next(
                                (i for i, name in enumerate(fd_template_header)
                                 if str(name).strip().casefold() in {"entry id", "entry_id", "entryid"}),
                                None
                            )
                            contest_id_index = next(
                                (i for i, name in enumerate(fd_template_header)
                                 if str(name).strip().casefold() in {"contest id", "contest_id", "contestid"}),
                                None
                            )
                            contest_name_index = next(
                                (i for i, name in enumerate(fd_template_header)
                                 if str(name).strip().casefold() in {"contest name", "contest_name", "contest"}),
                                None
                            )
                            if entry_id_index is None or contest_id_index is None:
                                raise ValueError("The FanDuel template must include Entry ID and Contest ID columns.")

                            target_id = str(selected_fd_contest.get("id", "")).strip()
                            target_name = str(selected_fd_contest.get("name", "")).strip()
                            target_rows = []
                            for row_index in range(1, fd_entry_end):
                                row = fd_template_rows[row_index]
                                row = list(row[:len(fd_template_header)]) + [""] * max(0, len(fd_template_header) - len(row))
                                if str(row[contest_id_index]).strip() != target_id:
                                    continue
                                if contest_name_index is not None and str(row[contest_name_index]).strip() != target_name:
                                    continue
                                target_rows.append(row_index)

                            if not target_rows:
                                raise ValueError(
                                    "No existing entries match the selected contest in this template. "
                                    "Please select the contest that matches the uploaded file."
                                )
                            if len(fd_all_ranked) < len(target_rows):
                                raise ValueError(
                                    f"This contest has {len(target_rows)} of your entries, but the build contains "
                                    f"only {len(fd_all_ranked)} lineups. Build at least that many so every entry is replaced."
                                )

                            # Only replace existing entries; never create extra entries.
                            # Use the FanDuel ID from the uploaded salary file in each roster cell.
                            for entry_number, row_index in enumerate(target_rows):
                                lineup = fd_all_ranked.iloc[entry_number]
                                row = list(fd_template_rows[row_index][:len(fd_template_header)])
                                row.extend([""] * (len(fd_template_header) - len(row)))
                                for slot_index, (slot_name, _) in zip(roster_column_indices, slot_aliases):
                                    player_name = str(lineup[slot_name])
                                    player_id = str(fd_ids.get(player_name, "")).strip()
                                    if not player_id or player_id.lower() == "nan":
                                        raise ValueError(f"Missing FanDuel player ID for {player_name}.")
                                    # FanDuel entry templates use slate-prefixed player IDs
                                    # (for example, 135282-62239). Add the selected slate prefix
                                    # when the salary file supplies only the numeric player ID.
                                    if "-" not in player_id and "-" in target_id:
                                        player_id = target_id.split("-", 1)[0] + "-" + player_id
                                    row[slot_index] = player_id
                                fd_template_rows[row_index] = row

                            output = io.StringIO(newline="")
                            csv.writer(output, lineterminator="\\n").writerows(fd_template_rows)
                            st.success(
                                f"Replacement file ready: {len(target_rows)} existing entries will be updated "
                                f"for {target_name}. Entry IDs and contest details are preserved."
                            )
                            st.download_button(
                                "DOWNLOAD FANDUEL REPLACEMENT CSV",
                                output.getvalue().encode("utf-8"),
                                file_name=("FanDuel_Single_Game_Replacement.csv" if lineup_mode == "Single Game"
                                           else "FanDuel_Full_Roster_Replacement.csv"),
                                mime="text/csv",
                                key="fd_export_" + lineup_mode.replace(" ", "_").lower()
                            )
                        except Exception as exc:
                            st.error(f"Could not create FanDuel replacement CSV: {exc}")
            else:
                st.info("This CSV has no player ID column, so lineup export is unavailable.")

        st.stop()

    # ================================
    # SETTINGS
    # ================================

    SIMULATIONS = SIMULATION_COUNT
    DISPERSION = 8.0
    SALARY_CAP = 50000

    # NFL DFS scoring settings. Lineup builders use these site/format rules.
    # Player outcomes are still generated from the app's internal estimates; this
    # defines the fantasy-point scoring model and the single-game multiplier.
    DFS_SCORING_RULES = {
        "DraftKings": {
            "pass_yard": 0.04, "pass_td": 4, "interception": -1,
            "rush_yard": 0.1, "rush_td": 6,
            "receiving_yard": 0.1, "receiving_td": 6, "reception": 1,
            "fumble_lost": -1, "two_point_conversion": 2,
            "pass_300_bonus": 3, "rush_100_bonus": 3, "receiving_100_bonus": 3,
            "single_game_multiplier": 1.5,
            "sack": 1, "def_interception": 2, "fumble_recovery": 2,
            "defensive_td": 6, "safety": 2, "blocked_kick": 2,
        },
        "FanDuel": {
            "pass_yard": 0.04, "pass_td": 4, "interception": -1,
            "rush_yard": 0.1, "rush_td": 6,
            "receiving_yard": 0.1, "receiving_td": 6, "reception": 0.5,
            "fumble_lost": -2, "two_point_conversion": 2,
            "pass_300_bonus": 0, "rush_100_bonus": 0, "receiving_100_bonus": 0,
            "single_game_multiplier": 1.5,
            "sack": 1, "def_interception": 2, "fumble_recovery": 2,
            "defensive_td": 6, "safety": 2, "blocked_kick": 2,
        },
    }

    def score_nfl_stat_line(stats, platform):
        """Apply DraftKings or FanDuel NFL scoring to simulated player stat lines."""
        rules = DFS_SCORING_RULES["FanDuel" if str(platform).lower().startswith("fanduel") else "DraftKings"]
        arr = lambda key: np.asarray(stats.get(key, 0), dtype=float)
        passing_yards, rushing_yards, receiving_yards = arr("passing_yards"), arr("rushing_yards"), arr("receiving_yards")
        score = (
            passing_yards * rules["pass_yard"]
            + arr("passing_tds") * rules["pass_td"]
            + arr("interceptions") * rules["interception"]
            + rushing_yards * rules["rush_yard"]
            + arr("rushing_tds") * rules["rush_td"]
            + receiving_yards * rules["receiving_yard"]
            + arr("receiving_tds") * rules["receiving_td"]
            + arr("receptions") * rules["reception"]
            + arr("fumbles_lost") * rules["fumble_lost"]
            + arr("two_point_conversions") * rules["two_point_conversion"]
            + arr("sacks") * rules["sack"]
            + arr("def_interceptions") * rules["def_interception"]
            + arr("fumble_recoveries") * rules["fumble_recovery"]
            + arr("defensive_tds") * rules["defensive_td"]
            + arr("safeties") * rules["safety"]
            + arr("blocked_kicks") * rules["blocked_kick"]
        )
        score = score + (passing_yards >= 300) * rules["pass_300_bonus"]
        score = score + (rushing_yards >= 100) * rules["rush_100_bonus"]
        score = score + (receiving_yards >= 100) * rules["receiving_100_bonus"]
        # Kicker scoring: 3 points for short FGs, 4 for 40-49 yards, 5 for 50+.
        score = score + arr("fg_under_40") * 3 + arr("fg_40_49") * 4 + arr("fg_50_plus") * 5
        score = score + arr("extra_points_made")
        # Defense scoring includes points-allowed tiers; yardage allowed is modeled too.
        points_allowed = arr("points_allowed")
        score = score + np.select(
            [points_allowed == 0, points_allowed <= 6, points_allowed <= 13,
             points_allowed <= 20, points_allowed <= 27, points_allowed <= 34],
            [10, 7, 4, 1, 0, -1], default=-4
        ) * np.asarray(stats.get("is_defense", 0), dtype=float)
        if not str(platform).lower().startswith("fanduel"):
            yards_allowed = arr("yards_allowed")
            score = score + np.select(
                [yards_allowed <= 100, yards_allowed <= 199, yards_allowed <= 299,
                 yards_allowed <= 349, yards_allowed <= 399, yards_allowed <= 449,
                 yards_allowed <= 499],
                [3, 2, 1, 0, -1, -3, -5], default=-7
            ) * np.asarray(stats.get("is_defense", 0), dtype=float)
        return score


    def _simulate_scored_player_outcomes(players_df, platform, rng):
        """Simulate player outcomes from historical distributions and shared game scripts.

        Projections help set volatility and reasonable upper bounds, but do not force
        simulated averages to equal the supplied projection.
        """
        simulation_progress = st.progress(0, text="Preparing player simulations...")
        historical = load_nfl_historical_player_stats()
        historical_name_index = _build_historical_name_index(historical)
        simulation_progress.progress(0.05, text="Historical data loaded. Preparing game scripts...")
        simulations = {}
        cap_hit_percentages = {}
        n = SIMULATIONS
        correlation_strength = float(
            np.clip(st.session_state.get("active_game_correlation_strength", 1.0), 0.0, 1.0)
        )

        # Calibrate shared game environments from actual NFL game scores in play-by-play.
        # PBP is cached for 24 hours; if it cannot be reached, fall back to the existing
        # player-week history so simulations can still run.
        historical_game_factors = np.array([], dtype=float)
        pbp_status_box = st.empty()
        pbp_status_box.info("Loading NFL play-by-play history...")
        pbp_history = load_nfl_pbp_game_history()
        pbp_status_box.info("Play-by-play history: " + st.session_state.get(
            "nfl_pbp_history_status", "Status not available yet."
        ))
        if not pbp_history.empty and "GamePoints" in pbp_history.columns:
            try:
                game_totals = pd.to_numeric(pbp_history["GamePoints"], errors="coerce").dropna()
                game_totals = game_totals[game_totals > 0].to_numpy(dtype=float)
                if len(game_totals) >= 20:
                    center = float(np.median(game_totals))
                    if np.isfinite(center) and center > 0:
                        historical_game_factors = np.clip(game_totals / center, 0.75, 1.25)
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
                        center = float(np.median(game_totals))
                        if np.isfinite(center) and center > 0:
                            historical_game_factors = np.clip(game_totals / center, 0.75, 1.25)
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
            if historical_result is not None:
                historical_points, recency_weights = historical_result
                probabilities = recency_weights / recency_weights.sum()
                scores = rng.choice(
                    historical_points, size=n, replace=True, p=probabilities
                ).astype(float)

            # Anchor sparse/no-history players to a projection-informed distribution.
            # Without this, generic position stat lines can greatly overshoot tiny
            # projections and then get clipped to a flat 3-point ceiling.
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
                # Preserve the shape of the generated stat-line outcomes, but scale
                # the generic position baseline toward the player's actual projection.
                # Add modest independent noise so low-projection players don't become
                # identical values across every simulated percentile.
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
                        # Preserve the historical/sample mean instead of forcing
                        # simulated outcomes to average the supplied projection.
                        scores = projection + standardized
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

        # Add a direct QB-to-pass-catcher relationship on top of the shared
        # team/game scripts above. A QB's high or low passing outcome should
        # move his team's WR/TE outcomes in the same direction. Standardizing
        # the QB outcome avoids using raw points across players with different
        # scoring ranges. This is a lightweight covariance layer, not a play-by-play
        # model; the effect is controlled by the existing correlation slider.
        if correlation_strength > 0 and not players_df.empty:
            team_col = "Team" if "Team" in players_df.columns else None
            position_col = "Position" if "Position" in players_df.columns else None
            name_col = "Name" if "Name" in players_df.columns else None
            if team_col and position_col and name_col:
                for team, team_rows in players_df.groupby(
                    players_df[team_col].astype(str).str.upper().str.strip()
                ):
                    qb_names = team_rows[
                        team_rows[position_col].astype(str).str.upper().str.contains(r"\bQB\b", regex=True)
                    ][name_col].astype(str).tolist()
                    if not qb_names:
                        continue
                    qb_name = next((name for name in qb_names if name in simulations), None)
                    if qb_name is None:
                        continue
                    qb_scores = np.asarray(simulations[qb_name], dtype=float)
                    qb_std = float(np.std(qb_scores))
                    if not np.isfinite(qb_std) or qb_std < 1e-6:
                        continue
                    qb_z = np.clip((qb_scores - float(np.mean(qb_scores))) / qb_std, -2.5, 2.5)
                    pass_catchers = team_rows[
                        team_rows[position_col].astype(str).str.upper().str.contains(r"\b(WR|TE)\b", regex=True)
                    ][name_col].astype(str).tolist()
                    for catcher_name in pass_catchers:
                        if catcher_name not in simulations or catcher_name == qb_name:
                            continue
                        catcher_scores = np.asarray(simulations[catcher_name], dtype=float)
                        catcher_std = float(np.std(catcher_scores))
                        if not np.isfinite(catcher_std) or catcher_std < 1e-6:
                            continue
                        # Moderate direct correlation avoids making every receiver
                        # mirror the QB while still rewarding coherent passing spikes.
                        rho = 0.18 * correlation_strength
                        simulations[catcher_name] = np.maximum(
                            catcher_scores + rho * catcher_std * qb_z,
                            0.0,
                        )

        result = pd.DataFrame(simulations)
        st.session_state["simulation_cap_hit_pct"] = cap_hit_percentages
        simulation_progress.progress(1.0, text=f"Player simulations complete: {total_players} players")

        return result

else:

    # ================================
    # SETTINGS
    # ================================

    SIMULATIONS = SIMULATION_COUNT
    DISPERSION = 8.0
    SALARY_CAP = 50000

    # NFL DFS scoring settings. Lineup builders use these site/format rules.
    # Player outcomes are still generated from the app's internal estimates; this
    # defines the fantasy-point scoring model and the single-game multiplier.
    DFS_SCORING_RULES = {
        "DraftKings": {
            "pass_yard": 0.04, "pass_td": 4, "interception": -1,
            "rush_yard": 0.1, "rush_td": 6,
            "receiving_yard": 0.1, "receiving_td": 6, "reception": 1,
            "fumble_lost": -1, "two_point_conversion": 2,
            "pass_300_bonus": 3, "rush_100_bonus": 3, "receiving_100_bonus": 3,
            "single_game_multiplier": 1.5,
            "sack": 1, "def_interception": 2, "fumble_recovery": 2,
            "defensive_td": 6, "safety": 2, "blocked_kick": 2,
        },
        "FanDuel": {
            "pass_yard": 0.04, "pass_td": 4, "interception": -1,
            "rush_yard": 0.1, "rush_td": 6,
            "receiving_yard": 0.1, "receiving_td": 6, "reception": 0.5,
            "fumble_lost": -2, "two_point_conversion": 2,
            "pass_300_bonus": 0, "rush_100_bonus": 0, "receiving_100_bonus": 0,
            "single_game_multiplier": 1.5,
            "sack": 1, "def_interception": 2, "fumble_recovery": 2,
            "defensive_td": 6, "safety": 2, "blocked_kick": 2,
        },
    }

    def score_nfl_stat_line(stats, platform):
        """Apply DraftKings or FanDuel NFL scoring to simulated player stat lines."""
        rules = DFS_SCORING_RULES["FanDuel" if str(platform).lower().startswith("fanduel") else "DraftKings"]
        arr = lambda key: np.asarray(stats.get(key, 0), dtype=float)
        passing_yards, rushing_yards, receiving_yards = arr("passing_yards"), arr("rushing_yards"), arr("receiving_yards")
        score = (
            passing_yards * rules["pass_yard"]
            + arr("passing_tds") * rules["pass_td"]
            + arr("interceptions") * rules["interception"]
            + rushing_yards * rules["rush_yard"]
            + arr("rushing_tds") * rules["rush_td"]
            + receiving_yards * rules["receiving_yard"]
            + arr("receiving_tds") * rules["receiving_td"]
            + arr("receptions") * rules["reception"]
            + arr("fumbles_lost") * rules["fumble_lost"]
            + arr("two_point_conversions") * rules["two_point_conversion"]
            + arr("sacks") * rules["sack"]
            + arr("def_interceptions") * rules["def_interception"]
            + arr("fumble_recoveries") * rules["fumble_recovery"]
            + arr("defensive_tds") * rules["defensive_td"]
            + arr("safeties") * rules["safety"]
            + arr("blocked_kicks") * rules["blocked_kick"]
        )
        score = score + (passing_yards >= 300) * rules["pass_300_bonus"]
        score = score + (rushing_yards >= 100) * rules["rush_100_bonus"]
        score = score + (receiving_yards >= 100) * rules["receiving_100_bonus"]
        # Kicker scoring: 3 points for short FGs, 4 for 40-49 yards, 5 for 50+.
        score = score + arr("fg_under_40") * 3 + arr("fg_40_49") * 4 + arr("fg_50_plus") * 5
        score = score + arr("extra_points_made")
        # Defense scoring includes points-allowed tiers; yardage allowed is modeled too.
        points_allowed = arr("points_allowed")
        score = score + np.select(
            [points_allowed == 0, points_allowed <= 6, points_allowed <= 13,
             points_allowed <= 20, points_allowed <= 27, points_allowed <= 34],
            [10, 7, 4, 1, 0, -1], default=-4
        ) * np.asarray(stats.get("is_defense", 0), dtype=float)
        if not str(platform).lower().startswith("fanduel"):
            yards_allowed = arr("yards_allowed")
            score = score + np.select(
                [yards_allowed <= 100, yards_allowed <= 199, yards_allowed <= 299,
                 yards_allowed <= 349, yards_allowed <= 399, yards_allowed <= 449,
                 yards_allowed <= 499],
                [3, 2, 1, 0, -1, -3, -5], default=-7
            ) * np.asarray(stats.get("is_defense", 0), dtype=float)
        return score


    def _simulate_scored_player_outcomes(players_df, platform, rng):
        """Simulate player outcomes from historical distributions and shared game scripts.

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
                game_totals = pd.to_numeric(pbp_history["GamePoints"], errors="coerce").dropna()
                game_totals = game_totals[game_totals > 0].to_numpy(dtype=float)
                if len(game_totals) >= 20:
                    center = float(np.median(game_totals))
                    if np.isfinite(center) and center > 0:
                        historical_game_factors = np.clip(game_totals / center, 0.75, 1.25)
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
            if historical_result is not None:
                historical_points, recency_weights = historical_result
                probabilities = recency_weights / recency_weights.sum()
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
                        # Preserve the historical/sample mean instead of forcing
                        # simulated outcomes to average the supplied projection.
                        scores = projection + standardized
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

    # ================================
    # PLAYER POOL
    # ================================

    players_df = pd.DataFrame([
        ["Dak Prescott", "QB", "DAL", 10400, 21.3],
        ["CeeDee Lamb", "WR", "DAL", 11800, 19.9],
        ["Javonte Williams", "RB", "DAL", 10800, 18.9],
        ["Jalon Daniels", "QB", "TB", 8600, 15.8],
        ["George Pickens", "WR", "DAL", 9400, 14.2],
        ["Bucky Irving", "RB", "TB", 8400, 12.3],
        ["Emeka Egbuka", "WR", "TB", 8200, 9.0],
        ["Ryan Flournoy", "WR", "DAL", 3800, 8.3],
        ["Jake Ferguson", "TE", "DAL", 7600, 8.0],
        ["Chris Godwin Jr.", "WR", "TB", 7200, 7.8],
        ["Cowboys", "DST", "DAL", 4800, 7.1],
        ["Cade Otton", "TE", "TB", 4400, 7.1],
        ["Kenny Gainwell", "RB", "TB", 4000, 6.6],
        ["Ted Hurst III", "WR", "TB", 2800, 5.4],
        ["Buccaneers", "DST", "TB", 3600, 4.4],
        ["Tyler Goodson", "RB", "DAL", 2600, 4.1],
        ["Tez Johnson", "WR", "TB", 2400, 3.5],
        ["KaVontae Turpin", "WR", "DAL", 1200, 1.5],
        ["Sean Tucker", "RB", "TB", 2000, 1.5],
        ["Brevyn Spann-Ford", "TE", "DAL", 1600, 1.4],
        ["Luke Schoonmaker", "TE", "DAL", 1400, 1.3],
        ["Hunter Luepke", "RB", "DAL", 1000, 0.9],
        ["Jonathan Mingo", "WR", "DAL", 1000, 0.9],
        ["Bauer Sharp", "TE", "TB", 800, 0.4],
        ["Kameron Johnson", "WR", "TB", 600, 0.4],
        ["Payne Durham", "TE", "TB", 200, 0.2],
        ["Brandon Aubrey", "K", "DAL", 5400, 8.0],
        ["Chase McLaughlin", "K", "TB", 5000, 7.0],
    ], columns=[
        "Name",
        "Position",
        "Team",
        "Salary",
        "Projection"
    ])

    # ================================
    # DRAFTKINGS SALARY FILE UPLOAD
    # ================================

    st.divider()
    st.write("### DraftKings Salary CSV")
    st.caption("Upload the salary CSV downloaded from DraftKings. The player pool and salaries will be loaded from this file.")
    salary_file = st.file_uploader(
        "Upload DraftKings Salary CSV",
        type=["csv"],
        help="Upload the DraftKings salary CSV for the single game you want to build lineups for.",
        key="dk_optional_salary_file",
    )

    entry_file = st.file_uploader(
        "Upload DraftKings Contest Entry File",
        type=["csv"],
        key="dk_contest_entry_file",
        help="Upload the CSV downloaded from DraftKings My Contests. The app will identify the contests included in the file."
    )

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
                st.stop()

            raw_header = [str(col).strip() for col in parsed_rows[0]]
            header_lookup = {str(col).strip().casefold(): i for i, col in enumerate(raw_header)}
            required_header_names = {"entry id", "contest name", "contest id", "entry fee"}
            if not required_header_names.issubset(header_lookup):
                st.error(
                    "This CSV does not appear to be a DraftKings My Contests entry file. "
                    "Please upload the original contest entry CSV, not the salary CSV."
                )
                st.stop()

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
                st.stop()

            # Validate the uploaded contest-entry template against the selected format.
            normalized_slots = [str(slot).strip().upper() for slot in roster_headers]
            entry_is_showdown = any(slot == "CPT" for slot in normalized_slots)
            if lineup_mode == "Showdown" and not entry_is_showdown:
                st.error(
                    "This is not a DraftKings Showdown entry file: its roster columns do not include CPT. "
                    "Select DraftKings Classic or upload the correct Showdown entries file."
                )
                st.stop()
            if lineup_mode == "Classic" and entry_is_showdown:
                st.error(
                    "This is a DraftKings Showdown entry file (CPT/FLEX), but DraftKings Classic is selected. "
                    "Select DraftKings Showdown or upload the correct Classic entries file."
                )
                st.stop()

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
                st.stop()

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
                # No contest dropdown: use the first unique contest in the uploaded entry CSV.
                # Users can upload a file containing only the contest they want to target.
                if contest_summary.empty:
                    st.warning("No usable contest rows were found in this entry CSV. Please upload the original DraftKings My Contests CSV.")
                    selected_row = pd.Series({"Contest ID": "", "Contest Name": "", "Entries": len(entry_df), "EntryFee": None})
                else:
                    selected_row = contest_summary.iloc[0]
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
            "field_size": None,
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
        st.caption("Upload your DraftKings contest entry CSV if you want to target existing entries.")

    dk_saved_contests[dk_slate_key] = active_dk_selection
    st.session_state["selected_dk_contests_by_slate"] = dk_saved_contests
    st.session_state["selected_dk_contest"] = active_dk_selection

    # The sampled opponent field is used to estimate the full contest, not to
    # pretend the sample is the actual contest size.
    previous_field_size = active_dk_selection.get("field_size")
    try:
        default_field_size = int(previous_field_size) if previous_field_size else 45396
    except (TypeError, ValueError):
        default_field_size = 45396
    active_field_size = st.number_input(
        "Current total contest entries (update from DraftKings lobby)",
        min_value=2,
        max_value=200000,
        value=max(2, min(200000, default_field_size)),
        step=100,
        key=f"dk_field_size_{dk_slate_key}",
        help="Enter the current total entries shown in the DraftKings lobby, including your entries."
    )
    active_dk_selection["field_size"] = int(active_field_size)
    dk_saved_contests[dk_slate_key] = active_dk_selection
    st.session_state["selected_dk_contests_by_slate"] = dk_saved_contests
    st.session_state["selected_dk_contest"] = active_dk_selection

    dk_opponent_target = get_contest_opponent_target("dk")
    st.caption(
        f"Simulated opponent sample: up to {dk_opponent_target:,}; "
        f"estimated full contest: {int(active_field_size):,} total entries."
    )

    st.write("### Projection Sources")

    # Optional uploaded projection files; automatic public-source refresh is handled
    # by apply_external_projection_sources when these are not supplied.
    dff_projection_file = None
    draftedge_projection_file = None
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
            st.error(f"Could not read that CSV: {exc}. The sample player pool is still being used.")

    @st.cache_data(show_spinner=False, ttl=86400)
    def _download_nfl_historical_player_stats():
        """Download historical NFL stats once per cache period, with a network timeout."""
        import io
        import requests

        frames = []
        loaded_seasons = []
        errors = []
        # Use three recent completed seasons. This provides more player history while
        # keeping the download bounded; Streamlit caches the result for 24 hours.
        # Short per-request timeouts ensure unavailable data falls back promptly.
        for season in [2025, 2024, 2023]:
            url = f"https://github.com/nflverse/nflverse-data/releases/download/player_stats/stats_player_week_{season}.csv"
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
        """Load compact final-score history from nflverse play-by-play, cached for 24 hours."""
        import requests

        frames = []
        loaded_seasons = []
        errors = []
        # Use recent historical seasons for game-environment calibration.
        # Streamlit caches the completed result for 24 hours to avoid repeat downloads.
        wanted_columns = {
            "season", "game_id", "play_id", "total_home_score", "total_away_score",
            "game_seconds_remaining", "qtr"
        }
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
                required = {"game_id", "total_home_score", "total_away_score"}
                if frame.empty or not required.issubset(frame.columns):
                    errors.append(f"{season}: play-by-play file did not contain required score columns")
                    continue
                frame["season"] = season
                frame["_play_order"] = pd.to_numeric(
                    frame.get("play_id", pd.Series(np.arange(len(frame)))), errors="coerce"
                )
                frame["_home_score"] = pd.to_numeric(frame["total_home_score"], errors="coerce")
                frame["_away_score"] = pd.to_numeric(frame["total_away_score"], errors="coerce")
                frame = frame.dropna(subset=["game_id", "_home_score", "_away_score"])
                final_scores = (
                    frame.sort_values("_play_order")
                    .groupby("game_id", sort=False)
                    .tail(1)
                    .copy()
                )
                final_scores["GamePoints"] = final_scores["_home_score"] + final_scores["_away_score"]
                final_scores = final_scores[["season", "game_id", "GamePoints"]]
                if not final_scores.empty:
                    frames.append(final_scores)
                    loaded_seasons.append(season)
            except Exception as exc:
                errors.append(f"{season}: {str(exc)[:120]}")
        history = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
            columns=["season", "game_id", "GamePoints"]
        )
        if not history.empty:
            history = history.drop_duplicates(subset=["game_id"], keep="last").reset_index(drop=True)
        return history, loaded_seasons, errors


    def load_nfl_pbp_game_history():
        """Return cached play-by-play game-score history, failing safely if unavailable."""
        try:
            history, loaded_seasons, errors = _download_nfl_pbp_game_history()
        except Exception as exc:
            history, loaded_seasons, errors = pd.DataFrame(), [], [str(exc)[:120]]
        st.session_state["nfl_pbp_history_status"] = (
            "Play-by-play game history loaded for seasons "
            + ", ".join(str(year) for year in loaded_seasons)
            + ". Cached for 24 hours."
            if loaded_seasons
            else "Play-by-play history unavailable; using historical player stats instead."
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
                "fumbles_lost": "sack_fumbles_lost",
            }
            scores = []
            for _, game in rows.iterrows():
                stat_line = {}
                for output_col, source_col in stats_map.items():
                    if source_col in rows.columns:
                        stat_line[output_col] = pd.to_numeric(pd.Series([game[source_col]]), errors="coerce").fillna(0).iloc[0]
                scores.append(float(score_nfl_stat_line(stat_line, platform)))
            points = np.asarray(scores, dtype=float)
        else:
            points_col = next((col for col in ["fantasy_points_ppr", "fantasy_points"] if col in rows.columns), None)
            if points_col is None:
                return None
            points = pd.to_numeric(rows[points_col], errors="coerce").fillna(0).to_numpy(dtype=float)
        weights = np.linspace(0.5, 1.5, len(points))
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


    players_df = apply_injury_statuses(players_df, "injury_status_dk_" + lineup_mode.replace(" ", "_").lower())

    # External projections only: do not calculate or use internal fallback projections.
    players_df["Projection"] = np.nan
    players_df = apply_external_projection_sources(
        players_df,
        dff_projection_file,
        draftedge_projection_file,
        platform_name=("DraftKings Showdown" if lineup_mode == "Showdown" else "DraftKings Classic"),
    )

    def internal_slate_key(frame):
        """Stable identity for an uploaded slate, independent of external projections."""
        return tuple(
            frame[["Name", "Team", "Position", "Salary"]]
            .astype(str)
            .itertuples(index=False, name=None)
        )

    players_df = exclude_zero_projection_players(players_df, "DraftKings " + lineup_mode)
    internal_key = internal_slate_key(players_df)
    st.caption("Projection values use the DFF/DraftEdge average when both are available, otherwise the single available source. Players without an external projection or with a zero projection are excluded.")
    if st.session_state.get("nfl_historical_stats_status"):
        st.caption(st.session_state["nfl_historical_stats_status"])
        if st.session_state.get("nfl_historical_players_matched") is not None:
            st.caption("Historical player matches in current pool: " + str(st.session_state["nfl_historical_players_matched"]))
    if st.session_state.get("nfl_pbp_history_status"):
        st.caption("Play-by-play history: " + st.session_state["nfl_pbp_history_status"])

    volatility_check = st.session_state.get("historical_volatility_check")
    if isinstance(volatility_check, pd.DataFrame) and not volatility_check.empty:
        with st.expander("Historical Volatility Check (rough diagnostic)", expanded=False):
            st.caption(
                "Compares recent weekly fantasy-score variation by position with the simulator's current target. "
                "It is a useful warning signal, not a true percentile backtest: archived pregame projections are unavailable, "
                "and historical scoring may differ from the selected site's scoring rules. Treat small samples cautiously."
            )
            st.dataframe(volatility_check, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Historical Volatility Check",
                data=volatility_check.to_csv(index=False).encode("utf-8"),
                file_name="historical_volatility_check.csv",
                mime="text/csv",
                key="download_historical_volatility_check",
            )

    opponent_source = uploaded_df if "uploaded_df" in locals() else None
    opponent_map = build_opponent_map(opponent_source, players_df["Team"])
    players_df["Opponent"] = players_df["Team"].map(opponent_map).fillna("—")

    players_df["CaptainSalary"] = (
        players_df["Salary"] * 1.5
    ).astype(int)

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
            st.stop()
        # Simulate stat lines first, then calculate fantasy points with site scoring.
        rng = np.random.default_rng()
        outcomes = _simulate_scored_player_outcomes(eligible_players, platform, rng)
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
    st.write("### Player Pool")

    player_display = players_df.copy()

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

    # Add simulated opponent-field ownership beside the user's own exposure columns.
    # The field table is created during Contest Sim and retained in session state.
    field_ownership_display = st.session_state.get("latest_field_ownership")
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
        player_display["Field Own %"] = player_display["Name"].astype(str).str.strip().map(field_own_map).round(1)
        if "Captain/MVP Ownership %" in field_ownership_display.columns and not (
            platform == "DraftKings" and lineup_mode == "Classic"
        ):
            field_captain_map = dict(zip(
                field_ownership_display["Name"].astype(str).str.strip(),
                pd.to_numeric(field_ownership_display["Captain/MVP Ownership %"], errors="coerce")
            ))
            player_display["Field CPT Own %"] = player_display["Name"].astype(str).str.strip().map(field_captain_map).round(1)
    else:
        player_display["Field Own %"] = np.nan
        if not (platform == "DraftKings" and lineup_mode == "Classic"):
            player_display["Field CPT Own %"] = np.nan

    if "simulation_df" in st.session_state:
        simulation_df = st.session_state["simulation_df"]

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
    control_display = player_display.copy()
    for required_column in ["Name", "Position", "Team", "Opponent"]:
        if required_column not in control_display.columns:
            control_display[required_column] = players_df[required_column].values
    display_settings = [
        ("Lock", False), ("Fade", False),
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

    st.write("### Player Controls & Exposure")
    st.caption("Everything is together here. Review current exposure, then change Min/Max Exp % to guide future builds. Lock includes a player; Fade excludes a player.")
    editable_control_columns = [setting for setting, _ in display_settings]
    disabled_control_columns = [
        column for column in control_display.columns
        if column not in editable_control_columns
    ]
    edited_player_controls = st.data_editor(
        control_display,
        use_container_width=True,
        hide_index=True,
        disabled=disabled_control_columns,
        column_config={
            "Name": st.column_config.TextColumn("Name", pinned=True),
            "Lock": st.column_config.CheckboxColumn("Lock", help="Force this player into lineup builds."),
            "Fade": st.column_config.CheckboxColumn("Fade", help="Keep this player out of lineup builds."),
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
            "Download this before kickoff. After the game, add an ActualPoints column "
            "with each player's fantasy points, then upload the file in Projection Accuracy Report."
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

    # Copy/paste-ready player pool export for sharing analysis in ChatGPT.
    with st.expander("Copy Player Info to ChatGPT"):
        st.caption("Copy the text below and paste it into ChatGPT. It includes player details, simulation stats, and Captain/Flex exposure when available.")
        # Export every column currently shown in the Player Pool, including any
        # additional projection/simulation/exposure fields added later.
        copy_df = player_display.copy()
        copy_text = copy_df.to_csv(index=False, sep="\t", na_rep="")
        st.text_area(
            "Player data (copy this text)",
            value=copy_text,
            height=350,
            key="dk_chatgpt_player_export_" + platform + "_" + lineup_mode,
            label_visibility="collapsed"
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
        "Lock", "Fade", "Min Exposure %", "Max Exposure %"
    ] + (
        [] if platform == "DraftKings" and lineup_mode == "Classic"
        else ["Captain Min %", "Captain Max %"]
    ):
        control_values[setting] = control_values["Name"].map(
            editor_controls[setting]
        ).fillna(control_values[setting])
    control_values["Lock"] = control_values["Lock"].astype(bool)
    control_values["Fade"] = control_values["Fade"].astype(bool)
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

    if "simulation_df" in st.session_state:
        simulation_df = st.session_state["simulation_df"]

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

    if platform == "DraftKings" and lineup_mode == "Classic":
        st.write("### DraftKings Classic Lineups")
        st.caption(
            "Classic roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), DST. "
            "Salary cap: $50,000. The 5,000-lineup build automatically spreads exposure instead of repeatedly selecting the same top players."
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

        build_cols = st.columns([1, 1, 0.65])
        with build_cols[0]:
            st.write("### Build Settings")
            dk_salary_range = st.slider(
                "Allowed lineup salary range",
                min_value=0,
                max_value=50000,
                value=(45000, 50000),
                step=100,
                format="$%d",
                key="dk_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),
                help="Only build lineups whose total salary falls inside this range."
            )
        MIN_LINEUP_SALARY, MAX_LINEUP_SALARY = dk_salary_range
        with build_cols[1]:
            aggressiveness_pct = st.slider(
                "Lineup Build Aggressiveness", 0, 100,
                100 if ((platform == "DraftKings" and lineup_mode == "Showdown") or (platform == "FanDuel" and lineup_mode == "Single Game")) else 50,
                step=5,
                help="Conservative favors steadier outcomes; aggressive favors ceiling and volatility. Does not change simulation or lineup counts.",
                key=f"lineup_build_aggressiveness_{platform}_{lineup_mode}",
            )
            aggressiveness = aggressiveness_pct / 100.0
            P95_WEIGHT = 0.60 - 0.30 * aggressiveness
            P99_WEIGHT = 0.10 + 0.45 * aggressiveness
            MEAN_WEIGHT = 1.0 - P95_WEIGHT - P99_WEIGHT
            STDDEV_WEIGHT = 0.10 * (2.0 * aggressiveness - 1.0)
            st.caption(f"Build style: {aggressiveness_pct}% aggressive · P95 {P95_WEIGHT:.0%} · P99 {P99_WEIGHT:.0%} · average {MEAN_WEIGHT:.0%} · volatility {STDDEV_WEIGHT:+.0%}.")

        with build_cols[2]:
            st.write("### Run")
            classic_run_all = st.button("SIM", type="primary", use_container_width=True, key="dk_classic_run_all")
        classic_workflow_status = None
        if classic_run_all:
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
                st.stop()

        build_clicked = classic_run_all

        if build_clicked and platform == "DraftKings" and lineup_mode == "Classic":
            rng = np.random.default_rng()
            rankings = {}
            for _, row in classic_pool.iterrows():
                player = row["Name"]
                rankings[player] = (
                    player_sim.get(player, {}).get("P95", row["Projection"]) * P95_WEIGHT
                    + player_sim.get(player, {}).get("P99", row["Projection"] * 2.3) * P99_WEIGHT
                    + player_sim.get(player, {}).get("Mean", row["Projection"]) * MEAN_WEIGHT
                    + player_sim.get(player, {}).get("StdDev", 0.0) * STDDEV_WEIGHT
                )
            classic_base_scores = np.asarray([rankings.get(str(name), 0.01) for name in classic_pool["Name"]], dtype=float)
            classic_adjusted_scores, classic_ownership_proxy = ownership_adjusted_player_scores(
                classic_pool, classic_pool["Name"].astype(str).tolist(), classic_base_scores, player_sim
            )
            rankings = {
                str(name): float(classic_adjusted_scores[i])
                for i, name in enumerate(classic_pool["Name"].astype(str).tolist())
            }
            classic_locked_players = [
                name for name in available_players
                if control_map.get(name, {}).get("Lock", False)
            ]
            ranked_names = list(dict.fromkeys(
                sorted(rankings, key=rankings.get, reverse=True)
                + classic_locked_players
            ))
            classic_pool = classic_pool[classic_pool["Name"].isin(ranked_names)].drop_duplicates("Name", keep="first").copy()
            classic_names = classic_pool["Name"].astype(str).to_numpy(dtype=object)
            classic_salaries = pd.to_numeric(classic_pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
            classic_eligible = classic_pool["Eligible"].tolist()
            classic_weights = np.asarray([max(rankings.get(name, 0.01), 0.01) for name in classic_names], dtype=float)
            classic_weights /= classic_weights.sum()
            classic_means = np.asarray([
                float(player_sim.get(name, {}).get("Mean", classic_pool.iloc[i]["Projection"]))
                for i, name in enumerate(classic_names)
            ], dtype=float)
            eligible_indices = {
                slot: np.asarray([i for i, positions in enumerate(classic_eligible) if positions & eligible], dtype=int)
                for slot, eligible in roster_slots
            }
            locked_name_set = set(classic_locked_players)
            locked_indices = {
                i for i, name in enumerate(classic_names) if name in locked_name_set
            }
            name_to_index = {str(name): i for i, name in enumerate(classic_names)}
            candidate_lineups = []
            seen = set()
            classic_build_counts = {str(name): 0 for name in classic_names}
            target_lineups = 5000
            # The old 500,000-attempt loop could look frozen after player simulation
            # completed. Unique Classic lineups are normally found much sooner; keep
            # the full 5,000-lineup target while bounding wasted duplicate/invalid tries.
            max_attempts = 100000
            build_progress = st.progress(0, text="Building DraftKings Classic lineups: 0 / 2,000")
            expected_exposure = max(1.0, target_lineups * len(roster_slots) / max(1, len(classic_names)))
            for attempt in range(max_attempts):
                chosen = {}
                used = set()
                salary = 0
                for slot, _eligible in roster_slots:
                    choices = np.asarray([
                        i for i in eligible_indices[slot]
                        if i not in used and salary + classic_salaries[i] <= MAX_LINEUP_SALARY
                    ], dtype=int)
                    if not len(choices):
                        break
                    weights = classic_weights[choices].copy()
                    exposure_penalty = np.asarray([
                        (1.0 + classic_build_counts.get(str(classic_names[i]), 0) / expected_exposure) ** 1.5
                        for i in choices
                    ], dtype=float)
                    weights /= exposure_penalty
                    weight_total = weights.sum()
                    if not np.isfinite(weight_total) or weight_total <= 0:
                        weights = np.full(len(choices), 1.0 / len(choices), dtype=float)
                    else:
                        weights /= weight_total
                    if rng.random() < 0.25:
                        picked = int(rng.choice(choices))
                    else:
                        picked = int(rng.choice(choices, p=weights))
                    chosen[slot] = str(classic_names[picked])
                    used.add(picked)
                    salary += int(classic_salaries[picked])
                if len(chosen) != len(roster_slots) or salary < MIN_LINEUP_SALARY or salary > MAX_LINEUP_SALARY or salary > 50000:
                    if attempt % 250 == 0:
                        build_progress.progress(
                            min(0.99, attempt / max_attempts),
                            text=f"Building DraftKings Classic lineups: {len(candidate_lineups):,} / {target_lineups:,} (checking valid rosters)"
                        )
                    continue
                if not locked_name_set.issubset(set(chosen.values())):
                    continue
                key = tuple(chosen[slot] for slot, _ in roster_slots)
                if key in seen:
                    continue
                seen.add(key)
                for player_name in set(chosen.values()):
                    classic_build_counts[str(player_name)] = classic_build_counts.get(str(player_name), 0) + 1
                selected_indices = [name_to_index[chosen[slot]] for slot, _ in roster_slots]
                projected_points = float(classic_means[selected_indices].sum())
                candidate_lineups.append({
                    **chosen, "Salary": salary, "ProjectedPoints": projected_points,
                    "Score": sum(rankings.get(name, 0.01) for name in chosen.values())
                })
                if len(candidate_lineups) % 100 == 0 or len(candidate_lineups) >= target_lineups:
                    build_progress.progress(
                        min(1.0, len(candidate_lineups) / target_lineups),
                        text=f"Building DraftKings Classic lineups: {len(candidate_lineups):,} / {target_lineups:,}"
                    )
                if len(candidate_lineups) >= target_lineups:
                    break
            build_progress.empty()

            if not candidate_lineups:
                st.error(
                    "No valid Classic lineups found. Check player positions, salaries, "
                    "locks, fades, and the uploaded salary file."
                )
            else:
                classic_results = pd.DataFrame(candidate_lineups).sort_values(
                    "Score", ascending=False
                ).reset_index(drop=True)
                st.session_state["classic_lineups"] = classic_results
                st.session_state["classic_pool_signature"] = slate_signature

        if classic_run_all and platform == "DraftKings" and lineup_mode == "Classic":
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
                    pool["Weight"] = pool["MeanPoints"].clip(lower=0.01)
                    contest_slots = [
                        ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                        ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                        ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}), ("DST", {"DST"})
                    ]
                    # Precompute NumPy arrays once. Avoid rebuilding/filtering a pandas
                    # DataFrame for every slot of every simulated opponent lineup.
                    pool_names = pool["Name"].astype(str).to_numpy(dtype=object)
                    pool_salaries = pd.to_numeric(pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
                    pool_weights = pd.to_numeric(pool["Weight"], errors="coerce").fillna(0.01).clip(lower=0.01).to_numpy(dtype=float)
                    pool_means = np.asarray([float(mean_scores.get(name, 0.0)) for name in pool_names], dtype=float)
                    slot_indices = {
                        slot: np.asarray([
                            i for i, positions in enumerate(pool["Eligible"].tolist())
                            if positions & eligible
                        ], dtype=np.int32)
                        for slot, eligible in contest_slots
                    }
                    rows = []
                    seen_contest = set()
                    attempts = 0
                    max_opponent_attempts = max(250000, dk_opponent_target * 15)
                    while len(rows) < dk_opponent_target and attempts < max_opponent_attempts:
                        attempts += 1
                        chosen_indices = []
                        chosen = {}
                        salary = 0
                        used = set()
                        for slot, _eligible in contest_slots:
                            base_indices = slot_indices[slot]
                            if not len(base_indices):
                                break
                            choices = base_indices[
                                np.asarray([
                                    int(i) not in used and salary + int(pool_salaries[i]) <= MAX_LINEUP_SALARY
                                    for i in base_indices
                                ], dtype=bool)
                            ]
                            if not len(choices):
                                break
                            weights = pool_weights[choices]
                            weight_sum = weights.sum()
                            if not np.isfinite(weight_sum) or weight_sum <= 0:
                                picked_idx = int(rng.choice(choices))
                            else:
                                picked_idx = int(rng.choice(choices, p=weights / weight_sum))
                            chosen[slot] = str(pool_names[picked_idx])
                            chosen_indices.append(picked_idx)
                            used.add(picked_idx)
                            salary += int(pool_salaries[picked_idx])
                        if len(chosen_indices) != len(contest_slots):
                            continue
                        if salary < MIN_LINEUP_SALARY or salary > MAX_LINEUP_SALARY or salary > 50000:
                            continue
                        key = tuple(chosen[slot] for slot, _ in contest_slots)
                        if key in seen_contest:
                            continue
                        seen_contest.add(key)
                        points = float(pool_means[chosen_indices].sum())
                        rows.append({**chosen, "Salary": salary, "ProjectedPoints": round(points, 2)})
                    contest_field_df = pd.DataFrame(rows)
                    user_lineups = st.session_state["classic_lineups"].copy()
                    opponent_scores = contest_field_df["ProjectedPoints"].to_numpy(dtype=float) if not contest_field_df.empty else np.array([])
                    if len(opponent_scores):
                        user_lineups = add_lineup_field_ownership(user_lineups)
                        user_lineups["BeatsOpponents"] = user_lineups["ProjectedPoints"].apply(lambda score: int(np.sum(opponent_scores < float(score))))
                        user_lineups["FieldPercentile"] = user_lineups["ProjectedPoints"].apply(lambda score: round(100.0 * np.mean(opponent_scores <= float(score)), 1))
                        user_lineups["FieldRank"] = user_lineups["ProjectedPoints"].apply(lambda score: 1 + int(np.sum(opponent_scores > float(score))))
                        user_lineups = add_field_ranking_metrics(user_lineups, opponent_scores)
                    st.session_state["classic_contest_field_df"] = contest_field_df
                    st.session_state["classic_contest_field_ready"] = len(contest_field_df) > 0
                    st.session_state["classic_contest_comparison_df"] = user_lineups
                if not contest_field_df.empty:
                    st.success(f"Compared your {len(user_lineups)} lineups against {len(contest_field_df):,} simulated opponent lineups.")
                    st.write("### Your Lineups vs. Contest Field")
                    st.caption("Comparison uses projected average points from the internal player simulations. It is an estimate, not actual contest results.")
                    st.dataframe(user_lineups, use_container_width=True, hide_index=True)
                    st.metric("Simulated opponent lineups", f"{len(contest_field_df):,}")
                    show_field_ownership(contest_field_df, [slot for slot, _ in contest_slots], "Simulated Field Player Ownership")
                else:
                    st.error("Could not create valid opponent lineups. Check the player pool and salary range.")
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
                classic_display,
                use_container_width=True,
                hide_index=True
            )

            # Classic portfolio controls match the larger portfolio selector used by other formats.
            st.divider()
            st.write("## Portfolio")
            st.caption("Choose how many generated Classic lineups to show and export. Up to 2,500 lineups can be selected.")
            classic_portfolio_source = st.session_state.get("classic_contest_comparison_df")
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
                max_value=min(2500, max(1, len(classic_portfolio_source))),
                value=min(2500, max(1, len(classic_portfolio_source))),
                step=100 if len(classic_portfolio_source) >= 100 else 1,
                key="dk_classic_portfolio_count"
            )
            classic_rank_label = st.selectbox(
                "Rank Classic lineups by",
                classic_rank_options,
                index=0,
                key="dk_classic_portfolio_metric"
            )
            classic_rank_metric = PORTFOLIO_METRICS[classic_rank_label]
            classic_top_portfolio = (
                classic_portfolio_source
                .drop_duplicates(
                    subset=[col for col in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
                            if col in classic_portfolio_source.columns],
                    keep="first"
                )
                .sort_values(classic_rank_metric, ascending=False)
                .head(int(classic_portfolio_count))
                .reset_index(drop=True)
            )
            st.caption(
                "These are estimated field-based rankings. Run CONTEST SIM first for the most useful comparison."
            )
            st.dataframe(classic_top_portfolio, use_container_width=True, hide_index=True)

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
                for _, lineup in classic_results.iterrows():
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
                    st.write("#### DraftKings Classic Export")
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
                            st.download_button(
                                label="DOWNLOAD FILE FOR EDIT ENTRIES",
                                data=export_df.to_csv(index=False).encode("utf-8"),
                                file_name="DraftKings_Classic_Contest_Entries.csv",
                                mime="text/csv",
                                use_container_width=True,
                                key="dk_classic_replace_export"
                            )
                            st.link_button(
                                "OPEN DRAFTKINGS MY LINEUPS / EDIT ENTRIES",
                                "https://www.draftkings.com/lineup",
                                use_container_width=True
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

        # Player Pool is rendered before the SIM button handler. After a fresh
        # simulation/build, rerun once so its Sim Pts and percentile columns read the
        # newly saved simulation_df instead of the previous run.
        if classic_run_all:
            st.rerun()
        st.stop()


# ============================================
# BUILD LINEUPS
# ============================================

# One-click workflow: SIM runs player simulations, builds the user's candidate lineups,
# builds the opponent field, then scores the contest.

build_cols = st.columns([1, 1, 0.65])
with build_cols[0]:
    st.write("### Build Settings")
    dk_salary_range = st.slider(
        "Allowed lineup salary range",
        min_value=0,
        max_value=50000,
        value=(45000, 50000),
        step=100,
        format="$%d",
        key="dk_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),
        help="Only build lineups whose total salary falls inside this range."
    )
MIN_LINEUP_SALARY, MAX_LINEUP_SALARY = dk_salary_range
with build_cols[1]:
    aggressiveness_pct = st.slider(
        "Lineup Build Aggressiveness", 0, 100,
        100 if ((platform == "DraftKings" and lineup_mode == "Showdown") or (platform == "FanDuel" and lineup_mode == "Single Game")) else 50,
        step=5,
        help="Conservative favors steadier outcomes; aggressive favors ceiling and volatility. Does not change simulation or lineup counts.",
        key=f"lineup_build_aggressiveness_{platform}_{lineup_mode}",
    )
    aggressiveness = aggressiveness_pct / 100.0
    P95_WEIGHT = 0.60 - 0.30 * aggressiveness
    P99_WEIGHT = 0.10 + 0.45 * aggressiveness
    MEAN_WEIGHT = 1.0 - P95_WEIGHT - P99_WEIGHT
    STDDEV_WEIGHT = 0.10 * (2.0 * aggressiveness - 1.0)
    st.caption(f"Build style: {aggressiveness_pct}% aggressive · P95 {P95_WEIGHT:.0%} · P99 {P99_WEIGHT:.0%} · average {MEAN_WEIGHT:.0%} · volatility {STDDEV_WEIGHT:+.0%}.")
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
        "SIM",
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
        st.stop()

# The eligible player pool was prepared before the SIM handler above.
# Keep the last successful candidate pool across Streamlit reruns.
candidates_df = st.session_state.get("candidates_df")

# ============================================
# RANK PLAYERS
# ============================================

if build_clicked:
    workflow_status.info("Step 2 of 4: Preparing rankings and building your candidate lineups...")
    try:
        showdown_base_scores = np.asarray([
            player_sim[p]["P95"] * P95_WEIGHT
            + player_sim[p]["P99"] * P99_WEIGHT
            + player_sim[p]["Mean"] * MEAN_WEIGHT
            + player_sim[p].get("StdDev", 0.0) * STDDEV_WEIGHT
            for p in available_players
        ], dtype=float)
        showdown_adjusted_scores, showdown_ownership_proxy = ownership_adjusted_player_scores(
            players_df[players_df["Name"].isin(available_players)].drop_duplicates("Name"),
            available_players, showdown_base_scores, player_sim
        )
        ownership_index = {name: i for i, name in enumerate(available_players)}
        showdown_rankings = {
            p: float(showdown_adjusted_scores[i]) for i, p in enumerate(available_players)
        }
        player_rank = sorted(available_players, key=lambda p: showdown_rankings[p], reverse=True)

        # Use top players plus all locked players, but weight candidates toward stronger captains.
        search_pool = list(dict.fromkeys(
            player_rank[:20] + locked_players
        ))
        rng = np.random.default_rng()

        # ============================================
        # CANDIDATE SETTINGS
        # ============================================

        LINEUP_COUNT = 2500
        CANDIDATE_COUNT = 5000

        # Rank-based probability curve: all captains retain a chance, but stronger
        # ranked players receive a larger share of candidate generation.
        player_rank_index = {p: i for i, p in enumerate(player_rank)}
        captain_weights = np.asarray(
            [1.0 / ((player_rank_index.get(p, len(player_rank)) + 1) ** 0.70) for p in search_pool],
            dtype=float
        )
        # Standard-deviation randomization adds variety to selection probabilities, not projections.
        captain_weights *= rng.lognormal(mean=0.0, sigma=0.25, size=len(captain_weights))
        captain_weights /= captain_weights.sum()
        captain_candidate_limits = {
            p: max(1, int(round(CANDIDATE_COUNT * captain_weights[i])))
            for i, p in enumerate(search_pool)
        }
        while sum(captain_candidate_limits.values()) > CANDIDATE_COUNT:
            largest = max(captain_candidate_limits, key=captain_candidate_limits.get)
            if captain_candidate_limits[largest] <= 1:
                break
            captain_candidate_limits[largest] -= 1

        # BUILD CANDIDATES
        # ============================================

        candidates = []

        candidate_progress = st.progress(0, text=f"Building weighted candidate lineups: 0 of {CANDIDATE_COUNT:,}")
        for captain_index, captain in enumerate(search_pool):
            captain_candidates = []
            per_captain_candidate_limit = captain_candidate_limits[captain]
            candidate_progress.progress(
                captain_index / max(1, len(search_pool)),
                text=f"Weighted search: captain {captain_index + 1} of {len(search_pool)} — {captain}"
            )

            if control_map[captain]["Captain Max %"] <= 0:
                continue

            # Keep captain search focused on the strongest ranked players, but allow every
            # eligible player into FLEX. Restricting FLEX to search_pool silently excluded
            # useful mid-ranked players (such as James Cook) from every generated lineup.
            flex_pool = [
                p for p in available_players
                if p != captain
            ]

            # Use a softer rank-based probability curve for FLEX selection.
            # Every player remains eligible, but higher-ranked players are sampled more often.
            flex_rank_weights = np.asarray(
                [1.0 / ((player_rank_index.get(p, len(player_rank)) + 1) ** 0.45) for p in flex_pool],
                dtype=float
            )
            # Standard-deviation randomization adds variety while preserving rank preference.
            flex_rank_weights *= rng.lognormal(mean=0.0, sigma=0.25, size=len(flex_rank_weights))
            flex_rank_weights /= flex_rank_weights.sum()

            seen_flex_groups = set()
            captain_attempts = 0
            # Keep the search bounded on Streamlit Cloud; repeated random samples can otherwise burn CPU for a long time when salary/lock rules reject most lineups.
            max_captain_attempts = max(500, per_captain_candidate_limit * 8)
            while (
                len(captain_candidates) < per_captain_candidate_limit
                and captain_attempts < max_captain_attempts
                and len(flex_pool) >= 5
            ):
                captain_attempts += 1
                if captain_attempts % 100 == 0:
                    candidate_progress.progress(
                        min(0.99, (captain_index + min(0.99, captain_attempts / max(1, max_captain_attempts))) / max(1, len(search_pool))),
                        text=f"Testing {captain}: {len(candidates) + len(captain_candidates):,} candidates accepted"
                    )
                sampled = rng.choice(
                    np.asarray(flex_pool, dtype=object),
                    size=5,
                    replace=False,
                    p=flex_rank_weights
                )
                flex_players = tuple(str(p) for p in sampled)
                flex_key = tuple(sorted(flex_players))
                if flex_key in seen_flex_groups:
                    continue
                seen_flex_groups.add(flex_key)

                lineup_players = [
                    captain
                ] + list(flex_players)

                # LOCK CHECK
                if not all(
                    p in lineup_players
                    for p in locked_players
                ):
                    continue

                # SALARY CHECK
                total_salary = (
                    captain_salary_map[captain]
                    + sum(
                        salary_map[p]
                        for p in flex_players
                    )
                )

                if total_salary < MIN_LINEUP_SALARY or total_salary > min(SALARY_CAP, MAX_LINEUP_SALARY):
                    continue

                # DraftKings Showdown requires players
                # from both teams
                lineup_teams = set(
                    players_df.loc[
                        players_df["Name"].isin(lineup_players),
                        "Team"
                    ]
                )

                if len(lineup_teams) < 2:
                    continue

                # ========================================
                # SIMULATION SCORE
                # ========================================

                total_mean = (
                    player_sim[captain]["Mean"] * 1.5
                    + sum(
                        player_sim[p]["Mean"]
                        for p in flex_players
                    )
                )

                total_p95 = (
                    player_sim[captain]["P95"] * 1.5
                    + sum(
                        player_sim[p]["P95"]
                        for p in flex_players
                    )
                )

                total_p99 = (
                    player_sim[captain]["P99"] * 1.5
                    + sum(
                        player_sim[p]["P99"]
                        for p in flex_players
                    )
                )

                raw_score = (
                    total_p95 * P95_WEIGHT
                    + total_p99 * P99_WEIGHT
                    + total_mean * MEAN_WEIGHT
                    + (
                        player_sim[captain].get("StdDev", 0.0) * 1.5
                        + sum(player_sim[p].get("StdDev", 0.0) for p in flex_players)
                    ) * STDDEV_WEIGHT
                )
                lineup_ownership = (
                    showdown_ownership_proxy[ownership_index[captain]] * 1.5
                    + sum(showdown_ownership_proxy[ownership_index[p]] for p in flex_players)
                )
                lineup_upside = max(0.0, total_p99 - total_p95)
                ownership_tax = max(0.0, lineup_ownership - 15.0 * 6.5) * 0.06
                upside_credit = min(ownership_tax, lineup_upside * 0.08)
                score = raw_score - ownership_tax + upside_credit

                captain_candidates.append({
                    "Captain": captain,
                    "Flex1": flex_players[0],
                    "Flex2": flex_players[1],
                    "Flex3": flex_players[2],
                    "Flex4": flex_players[3],
                    "Flex5": flex_players[4],
                    "Salary": total_salary,
                    "SimMean": total_mean,
                    "SimP95": total_p95,
                    "SimP99": total_p99,
                    "Score": score
                })

            candidates.extend(captain_candidates)
            candidate_progress.progress(
                min(0.99, (captain_index + 1) / max(1, len(search_pool))),
                text=f"Weighted candidates built: {len(candidates):,} of {CANDIDATE_COUNT:,}"
            )
            if len(candidates) >= CANDIDATE_COUNT:
                break

        candidates_df = pd.DataFrame(candidates)
        candidate_progress.progress(1.0, text=f"Candidate lineup search complete: {len(candidates_df):,} found")
    except Exception as exc:
        workflow_status.error(
            f"Step 2 failed while ranking players or building candidate lineups: {type(exc).__name__}: {exc}"
        )
        st.exception(exc)
        st.stop()


    st.session_state["candidates_df"] = candidates_df
    st.session_state["candidates_ready"] = True

if isinstance(candidates_df, pd.DataFrame):
    st.write(f"Candidate lineups tested: {len(candidates_df):,}")

if build_clicked:
    # Step 3: build the simulated opponent field after our candidate lineups exist.

    workflow_status.info(f"Step 3 of 4: Building up to {dk_opponent_target:,} simulated opponent lineups...")
    field_progress = st.progress(0, text=f"Step 3 of 4: Building opponent lineups (0 of {dk_opponent_target:,})...")
    try:
        contest_field_df = build_showdown_opponent_field(
            available_players, simulation_df, players_df, salary_map,
            captain_salary_map, SALARY_CAP, dk_opponent_target,
            progress_bar=field_progress
        )
    except Exception as exc:
        workflow_status.error(f"Step 3 failed while building opponent lineups: {type(exc).__name__}: {exc}")
        st.exception(exc)
        st.stop()
    field_progress.progress(1.0, text=f"Step 3 of 4 complete: {len(contest_field_df):,} opponent lineups created")
    if contest_field_df.empty:
        workflow_status.error(
            "Step 3 could not create any valid opponent lineups. Check the salary cap and eligible player pool."
        )
        st.stop()

    st.session_state["contest_field_df"] = contest_field_df
    st.session_state["contest_field_count"] = len(contest_field_df)
    st.session_state["contest_field_ready"] = (
        dk_opponent_target > 0 and len(contest_field_df) >= dk_opponent_target
    )

    selected_contest = st.session_state.get("selected_dk_contest")
    if selected_contest:
        st.info(
            f"Contest selected from your entry CSV: {selected_contest['name']} "
            f"(ID {selected_contest['id']}). Your uploaded file has "
            f"{selected_contest['your_entries']} of your entries in this contest. "
            f"The {dk_opponent_target:,} opponents are simulated; the entry CSV does not contain "
            "the actual opponent field or payout table."
        )



# Keep opponent ownership visible after Streamlit reruns, not only on the button-click run.
_saved_contest_field = st.session_state.get("contest_field_df")
if isinstance(_saved_contest_field, pd.DataFrame) and not _saved_contest_field.empty:
    st.subheader("Simulated Opponent Ownership")
    st.caption(
        f"Based on {len(_saved_contest_field):,} simulated opponent lineups. "
        "These percentages describe the simulated field, not your lineups."
    )
    show_field_ownership(
        _saved_contest_field,
        ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"],
        "Simulated Field Player Ownership",
        captain_slot="Captain",
    )


# ============================================
# CONTEST PAYOUT STRUCTURE
# ============================================
st.subheader("Contest Payout Structure")
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
    if st.button("FETCH DRAFTKINGS CONTEST DETAILS", key="fetch_dk_contest_details", use_container_width=True):
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

            # Some responses include structured payout tiers. Only accept tiers when
            # rank and prize values are explicit; never guess a full payout table from prose.
            _payout_rows = []
            _rank_keys = ("rank", "place", "position", "finish", "minRank", "min_rank", "startRank")
            _prize_keys = ("prize", "payout", "winnings", "amount", "prizeAmount", "payoutAmount")
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
                            if rank_num >= 1 and end_num >= rank_num and prize_num >= 0:
                                for rank in range(rank_num, min(end_num, 100000) + 1):
                                    _payout_rows.append((rank, prize_num))
                        except (TypeError, ValueError):
                            pass
                    for child in obj.values():
                        _walk_dk_payout_objects(child)
                elif isinstance(obj, list):
                    for child in obj:
                        _walk_dk_payout_objects(child)
            _walk_dk_payout_objects(_dk_payload)
            if _payout_rows:
                _payout_df = pd.DataFrame(_payout_rows, columns=["Rank", "Prize"]).drop_duplicates("Rank", keep="last")
                _payout_df = _payout_df.sort_values("Rank")
                _payout_schedule_auto = np.zeros(int(_payout_df["Rank"].max()), dtype=float)
                _payout_schedule_auto[_payout_df["Rank"].to_numpy(dtype=int) - 1] = _payout_df["Prize"].to_numpy(dtype=float)
                st.session_state["contest_payout_schedule"] = _payout_schedule_auto
                st.session_state["contest_payout_source_name"] = "DraftKings contest details API"
                st.session_state["contest_payout_contest_id"] = _contest_id_for_api
                st.session_state["contest_payout_auto_loaded"] = True
                st.success(f"DraftKings returned a structured payout table with {_payout_df['Rank'].nunique():,} ranks.")
            else:
                st.session_state["contest_payout_auto_loaded"] = False
                st.info(
                    "DraftKings returned contest details, but no complete rank-by-rank payout table was exposed. "
                    "Review the summary below and upload the payout table CSV to calculate expected prizes."
                )
            st.rerun()
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

payout_file = st.file_uploader(
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
        st.stop()

    if contest_field_df.empty:
        st.error(
            "No simulated opponent lineups were created, so contest scoring cannot run. "
            "Check the selected contest and player pool, then click SIM again."
        )
        st.stop()

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
    total_field = len(contest_idx)
    # The simulated field is a sample. Scale each sampled percentile to the
    # actual contest size before estimating full-field ranks and payouts.
    _selected_contest_for_scoring = st.session_state.get("selected_dk_contest", {}) or {}
    try:
        estimated_full_field_size = int(_selected_contest_for_scoring.get("field_size") or (total_field + 1))
    except (TypeError, ValueError):
        estimated_full_field_size = total_field + 1
    estimated_full_field_size = max(2, estimated_full_field_size)

    if build_clicked:
        workflow_status.info(
            f"Step 4 of 4: Scoring {n_candidates:,} candidate lineups against "
            f"{total_field:,} opponents across {n_sims:,} simulations..."
        )
    st.info(
        f"Candidate lineups are ready. Now scoring {n_candidates:,} lineups "
        f"against {total_field:,} simulated opponents across {n_sims:,} simulations. "
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

    progress = st.progress(0)
    # Convert once and score independent simulation batches concurrently.
    # All simulations and opponents are retained; parallelism changes only how
    # the work is scheduled, not the amount of work performed.
    simulation_values = simulation_df.to_numpy(dtype=np.float32, copy=False)
    batch_size = 128
    batch_ranges = [
        (batch_start, min(batch_start + batch_size, n_sims))
        for batch_start in range(0, n_sims, batch_size)
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

        # Sort every simulation's opponent scores together along the opponent axis.
        sorted_field = np.sort(batch_field_scores, axis=1)

        # Batched binary search: find each candidate's insertion position in its
        # simulation's sorted opponent scores. This preserves searchsorted(side="right")
        # behavior while avoiding a Python loop over every simulation.
        batch_count = batch_end - batch_start
        low = np.zeros((batch_count, n_candidates), dtype=np.int32)
        high = np.full((batch_count, n_candidates), total_field, dtype=np.int32)
        sim_rows = np.arange(batch_count)[:, None]

        while np.any(low < high):
            active = low < high
            mid = np.minimum((low + high) // 2, total_field - 1)
            mid_values = sorted_field[sim_rows, mid]
            move_right = (mid_values <= batch_candidate_scores) & active
            move_left = (mid_values > batch_candidate_scores) & active
            low = np.where(move_right, mid + 1, low)
            high = np.where(move_left, mid, high)

        count_greater = total_field - low
        percentiles = 1.0 - (count_greater / total_field)

        # Find the left insertion point too, so equal-scoring entries can share
        # the prize money for every rank occupied by the tie.
        left_low = np.zeros((batch_count, n_candidates), dtype=np.int32)
        left_high = np.full((batch_count, n_candidates), total_field, dtype=np.int32)
        while np.any(left_low < left_high):
            active_left = left_low < left_high
            mid_left = np.minimum((left_low + left_high) // 2, total_field - 1)
            mid_left_values = sorted_field[sim_rows, mid_left]
            move_right_left = (mid_left_values < batch_candidate_scores) & active_left
            move_left_left = (mid_left_values >= batch_candidate_scores) & active_left
            left_low = np.where(move_right_left, mid_left + 1, left_low)
            left_high = np.where(move_left_left, mid_left, left_high)

        # Estimate full-contest finishing ranks from each sampled-field percentile.
        # This is an approximation because the opponents are a capped sample.
        ranks = 1 + np.rint(
            (count_greater / total_field) * (estimated_full_field_size - 1)
        ).astype(np.int64)
        ranks = np.clip(ranks, 1, estimated_full_field_size)
        batch_win = np.sum(ranks == 1, axis=0, dtype=np.float64)
        batch_top1 = np.sum(ranks <= max(1, int(np.ceil(estimated_full_field_size * 0.01))), axis=0, dtype=np.float64)
        batch_top5 = np.sum(ranks <= max(1, int(np.ceil(estimated_full_field_size * 0.05))), axis=0, dtype=np.float64)
        batch_top10 = np.sum(ranks <= max(1, int(np.ceil(estimated_full_field_size * 0.10))), axis=0, dtype=np.float64)
        batch_percentiles = np.sum(percentiles, axis=0, dtype=np.float64)

        # Cash and payout ranks now refer to the estimated full contest, not
        # the smaller opponent sample. Without a contest payout table, retain
        # the conventional 10% paid estimate.
        paid_positions = (
            min(len(payout_schedule), estimated_full_field_size)
            if payout_schedule is not None
            else int(np.ceil(estimated_full_field_size * 0.10))
        )
        batch_cash = np.sum(ranks <= paid_positions, axis=0, dtype=np.float64)
        if payout_schedule is not None:
            # Approximate tie size by scaling the observed tie group to the full field.
            sampled_tie_counts = low - left_low + 1
            tie_counts = np.maximum(
                1,
                np.rint(sampled_tie_counts / total_field * estimated_full_field_size).astype(np.int64)
            )
            batch_prizes = np.zeros((batch_count, n_candidates), dtype=np.float64)
            max_tie_count = int(np.max(tie_counts)) if tie_counts.size else 1
            for tie_offset in range(min(max_tie_count, len(payout_schedule))):
                active_ties = tie_counts > tie_offset
                tie_ranks = ranks + tie_offset
                paid = active_ties & (tie_ranks <= len(payout_schedule))
                if np.any(paid):
                    prize_indices = np.minimum(tie_ranks - 1, len(payout_schedule) - 1)
                    batch_prizes += np.where(
                        paid,
                        payout_schedule[prize_indices] / tie_counts,
                        0.0
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
            progress.progress(completed_batches / len(batch_ranges))
            scoring_status.caption(
                f"Scoring contest: {completed_sims:,} of {n_sims:,} simulations complete "
                f"({completed_sims / n_sims:.0%}) using {max_workers} workers."
            )

    progress.empty()
    scoring_status.caption("Scoring complete. Building the ranked results table...")

    results_df = candidates_df.copy()

    results_df["WinRate"] = win_rates / n_sims
    results_df["Top1"] = top1_rates / n_sims
    results_df["Top5"] = top5_rates / n_sims
    results_df["Top10"] = top10_rates / n_sims
    results_df["CashRate"] = cash_rates / n_sims
    results_df["AvgPercentile"] = avg_percentiles / n_sims

    if payout_schedule is not None:
        results_df["Expected Prize ($)"] = expected_prize_totals / n_sims
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
        if total_field + 1 < _paid_positions_for_notice:
            st.warning(
                f"ROI warning: the payout table pays {_paid_positions_for_notice:,} places, but the simulation has only "
                f"{total_field:,} opponent lineups. That field is too small to estimate this contest's prizes reliably. "
                "Set the simulated opponent count to match the contest's actual field size, then run CONTEST SIM again."
            )
        else:
            st.success(
                "Expected Prize and ROI use the selected contest's payout table and simulated opponent lineups. "
                "Prize money is split across ranks when simulated entries tie; results remain estimates, not guaranteed winnings."
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

if "contest_results_df" in st.session_state and not (platform == "DraftKings" and lineup_mode == "Classic"):

    results_df = st.session_state["contest_results_df"]
    classic_mode = platform == "DraftKings" and lineup_mode == "Classic"
    portfolio_lineup_columns = (
        ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
        if classic_mode else ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
    )
    portfolio_lineup_columns = [col for col in portfolio_lineup_columns if col in results_df.columns]
    st.caption("Generate 5,000 candidates, then select up to 150 final lineups for your DraftKings contest.")

    portfolio_limit = min(150, len(results_df))
    portfolio_count = st.number_input(
        "Number of lineups",
        min_value=1,
        max_value=max(1, portfolio_limit),
        value=max(1, portfolio_limit),
        step=100 if portfolio_limit >= 100 else 1,
        key="portfolio_count"
    )

    portfolio_metric_label = st.selectbox(
        "Sort pool by",
        list(PORTFOLIO_METRICS.keys()),
        index=list(PORTFOLIO_METRICS.keys()).index("Top 1%"),
        key="portfolio_metric"
    )

    portfolio_metric = PORTFOLIO_METRICS[
        portfolio_metric_label
    ]

    current_control_signature = tuple(
        sorted(
            (
                str(name),
                float(values.get("Max Exposure %", 100)),
                float(values.get("Captain Max %", 100))
            )
            for name, values in control_map.items()
        )
    )
    if (
        "portfolio_df" not in st.session_state
        or st.session_state.get("portfolio_count_used") != portfolio_count
        or st.session_state.get("portfolio_control_signature") != current_control_signature
        or st.session_state.get("portfolio_metric_used") != portfolio_metric
    ):

        old_portfolio = st.session_state.get("portfolio_df")

        if (
            isinstance(old_portfolio, pd.DataFrame)
            and "Locked" in old_portfolio.columns
            and all(col in old_portfolio.columns for col in portfolio_lineup_columns)
        ):
            locked_df = old_portfolio[
                old_portfolio["Locked"] == True
            ].copy()

            available_count = max(
                0,
                int(portfolio_count) - len(locked_df)
            )

            lineup_columns = portfolio_lineup_columns
            ranked_df = (
                results_df
                .drop_duplicates(subset=lineup_columns, keep="first")
                .sort_values(
                    portfolio_metric,
                    ascending=False
                )
                .copy()
            )

            lineup_columns = portfolio_lineup_columns

            locked_keys = set(
                tuple(row)
                for row in locked_df[lineup_columns].to_numpy()
            )

            selected_rows = []

            for _, row in ranked_df.iterrows():

                key = tuple(
                    row[lineup_columns]
                )

                if key not in locked_keys:
                    selected_rows.append(row)

                if len(selected_rows) >= available_count:
                    break

            new_rows = pd.DataFrame(
                selected_rows
            )

            if len(new_rows) > 0:
                new_rows["Locked"] = False

            portfolio_df = pd.concat(
                [
                    locked_df,
                    new_rows
                ],
                ignore_index=True
            ).head(int(portfolio_count))

        else:
            # Rank candidates by the selected metric, then build a diversified
            # portfolio from those strong lineups. Prefer lineups that differ by
            # multiple players; if the candidate pool cannot fill the portfolio,
            # fill remaining spots with the next best unique lineups.
            ranked_df = (
                results_df
                .drop_duplicates(subset=portfolio_lineup_columns, keep="first")
                .sort_values(portfolio_metric, ascending=False, kind="stable")
                .reset_index(drop=True)
            )

            lineup_columns = portfolio_lineup_columns
            slot_count = len(lineup_columns)
            # Showdown has 6 roster spots; Classic has 9. Avoid near-duplicates
            # while keeping the selected lineups near the top of the chosen metric.
            max_shared_players = max(1, slot_count - 2)
            selected_indices = []
            selected_sets = []
            selected_keys = set()

            for idx, row in ranked_df.iterrows():
                lineup_key = tuple(str(row[col]) for col in lineup_columns)
                if lineup_key in selected_keys:
                    continue
                player_set = set(lineup_key)
                if all(
                    len(player_set.intersection(existing)) <= max_shared_players
                    for existing in selected_sets
                ):
                    selected_indices.append(idx)
                    selected_sets.append(player_set)
                    selected_keys.add(lineup_key)
                    if len(selected_indices) >= int(portfolio_count):
                        break

            # Fallback ensures the requested portfolio size can still be reached.
            if len(selected_indices) < int(portfolio_count):
                for idx, row in ranked_df.iterrows():
                    lineup_key = tuple(str(row[col]) for col in lineup_columns)
                    if lineup_key in selected_keys:
                        continue
                    selected_indices.append(idx)
                    selected_keys.add(lineup_key)
                    if len(selected_indices) >= int(portfolio_count):
                        break

            portfolio_df = ranked_df.iloc[selected_indices].copy().reset_index(drop=True)
            portfolio_df["Locked"] = False

        st.session_state["portfolio_df"] = portfolio_df
        st.session_state["portfolio_count_used"] = portfolio_count
        st.session_state["portfolio_metric_used"] = portfolio_metric
        st.session_state["portfolio_control_signature"] = current_control_signature

    # Changing the sort option must reorder the existing pool, not select a new one.
    # This keeps the exact same lineups while letting the user inspect a different ranking.
    portfolio_df = st.session_state["portfolio_df"].copy()
    if portfolio_metric in portfolio_df.columns:
        portfolio_df = portfolio_df.sort_values(
            portfolio_metric, ascending=False, kind="stable"
        ).reset_index(drop=True)
    st.session_state["portfolio_df"] = portfolio_df.copy()
    st.session_state["portfolio_metric_used"] = portfolio_metric
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
            "Total Sim Pts", "Lineup Ownership Score (%)", "Salary",
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

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # Show realized exposure in the final portfolio after Contest Sim.
    lineup_columns = [col for col in portfolio_lineup_columns if col in portfolio_df.columns]
    captain_count = (
        portfolio_df["Captain"].value_counts()
        if "Captain" in portfolio_df.columns else pd.Series(dtype=int)
    )
    total_lineups = len(portfolio_df)
    exposure_rows = []
    if total_lineups and lineup_columns:
        # Count portfolio appearances in one pass rather than repeatedly scanning
        # the portfolio once for every player in the full player pool.
        flat_portfolio_names = portfolio_df[lineup_columns].astype(str).to_numpy().ravel()
        appearance_counts = pd.Series(flat_portfolio_names).value_counts().to_dict()
        player_lookup = players_df.drop_duplicates("Name").set_index("Name", drop=False)
        for player_name, appearances in appearance_counts.items():
            if player_name not in player_lookup.index:
                continue
            player_row = player_lookup.loc[player_name]
            captain_appearances = int(captain_count.get(player_name, 0))
            exposure_rows.append({
                "Player": player_name,
                "Team": player_row.get("Team", ""),
                "Position": player_row.get("Position", ""),
                "Lineups": int(appearances),
                "Exposure %": round(100 * appearances / total_lineups, 1),
                "Captain Lineups": captain_appearances,
                "Captain %": round(100 * captain_appearances / total_lineups, 1)
            })

    st.write("### Final Portfolio Exposure")
    st.caption(
        "Exposure is based on your selected final portfolio, not the 5,000 candidates "
        "or the simulated opponent field."
    )
    if exposure_rows:
        exposure_df = pd.DataFrame(exposure_rows).sort_values(
            ["Exposure %", "Captain %", "Player"],
            ascending=[False, False, True]
        )
        st.dataframe(
            exposure_df,
            use_container_width=True,
            hide_index=True,
            column_config={"Player": st.column_config.TextColumn("Player", pinned=True)},
        )
        with st.expander("Copy Final Exposure to ChatGPT"):
            st.caption("Click inside the text box, press Ctrl+A, then Ctrl+C. Paste the copied text into ChatGPT.")
            st.text_area(
                "Final exposure data (copy this text)",
                value=exposure_df.to_csv(index=False, sep="\t", na_rep=""),
                height=300,
                key="chatgpt_final_exposure_export",
                label_visibility="collapsed"
            )
    else:
        st.info("Build a portfolio to see player exposure.")

    export_columns = [
        "Captain", "Captain Sim Pts", "Flex1", "Flex1 Sim Pts",
        "Flex2", "Flex2 Sim Pts", "Flex3", "Flex3 Sim Pts",
        "Flex4", "Flex4 Sim Pts", "Flex5", "Flex5 Sim Pts",
        "Salary", "Lineup Ownership Score (%)", "ContestScore", "WinRate", "Top1", "Top5",
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

    st.download_button(
        label="EXPORT PORTFOLIO CSV",
        data=portfolio_export_df.to_csv(index=False).encode("utf-8"),
        file_name="DFS_Portfolio.csv",
        mime="text/csv",
        use_container_width=True
    )


else:
    st.info(
        "Run CONTEST SIM before building a portfolio."
    )


# ============================================
# ============================================
# DRAFTKINGS SHOWDOWN EXPORT BUTTON
# Export the selected final portfolio using CPT and FLEX IDs from the uploaded DK template.
if platform == "DraftKings" and lineup_mode == "Showdown":
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
                st.write("#### DraftKings Showdown Export")
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
                        st.download_button(
                            label="DOWNLOAD FILE FOR EDIT ENTRIES",
                            data=export_df.to_csv(index=False).encode("utf-8"),
                            file_name="DraftKings_Showdown_Contest_Entries.csv",
                            mime="text/csv",
                            use_container_width=True,
                            key="dk_showdown_unified_export"
                        )
                        st.link_button(
                            "OPEN DRAFTKINGS MY LINEUPS / EDIT ENTRIES",
                            "https://www.draftkings.com/lineup",
                            use_container_width=True
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
    st.rerun()


# ============================================
# SIMMAH ROI TRACKER
# Tracks real entry fees and winnings. History can be exported and re-imported
# because Streamlit Cloud session storage may reset between visits.
st.divider()
st.header("SIMMAH ROI Tracker")
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
    roi_history_file = st.file_uploader(
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
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load that history file: {exc}")

with st.expander("Record a completed contest", expanded=True):
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
            st.rerun()
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
    st.dataframe(roi_history, use_container_width=True, hide_index=True)
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
