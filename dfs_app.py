import itertools
import re
import streamlit as st
import pandas as pd
import numpy as np
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="Universal DFS Simulator",
    page_icon="🏈",
    layout="wide"
)

st.title("Universal DFS Simulator")

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
    """Calculate player ownership percentages from simulated opponent lineups."""
    if field_df is None or field_df.empty:
        return pd.DataFrame(columns=["Name", "Ownership %", "Captain/MVP Ownership %"])
    valid_slots = [slot for slot in slots if slot in field_df.columns]
    total_lineups = len(field_df)
    if not valid_slots or total_lineups == 0:
        return pd.DataFrame(columns=["Name", "Ownership %", "Captain/MVP Ownership %"])
    # Vectorized counting avoids iterating over every row for large contest fields.
    slot_values = field_df[valid_slots].astype("string").apply(lambda col: col.str.strip())
    slot_values = slot_values.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    row_ids = np.repeat(np.arange(len(slot_values)), len(valid_slots))
    flat_names = slot_values.to_numpy(dtype=object).ravel()
    valid = pd.notna(flat_names) & ~np.isin(flat_names, ["", "nan", "None", "<NA>"])
    pairs = pd.DataFrame({"row": row_ids[valid], "name": flat_names[valid]}).drop_duplicates()
    counts = pairs["name"].value_counts().to_dict()
    captain_counts = {}
    if captain_slot and captain_slot in valid_slots:
        captain_values = slot_values[captain_slot].dropna()
        captain_values = captain_values[~captain_values.isin(["", "nan", "None", "<NA>"])]
        captain_counts = captain_values.value_counts().to_dict()
    names = sorted(set(counts) | set(captain_counts))
    return pd.DataFrame([{
        "Name": name,
        "Ownership %": round(100 * counts.get(name, 0) / total_lineups, 2),
        "Captain/MVP Ownership %": round(100 * captain_counts.get(name, 0) / total_lineups, 2),
    } for name in names]).sort_values("Ownership %", ascending=False).reset_index(drop=True)


def show_field_ownership(field_df, slots, title, captain_slot=None):
    ownership_df = calculate_field_ownership(field_df, slots, captain_slot)
    st.session_state["latest_field_ownership"] = ownership_df
    if not ownership_df.empty:
        st.write("### " + title)
        st.caption(f"Ownership calculated from {len(field_df):,} simulated opponent lineups. Captain/MVP ownership is shown separately where applicable.")
        st.dataframe(ownership_df, use_container_width=True, hide_index=True)


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
                                  salary_map, captain_salary_map, salary_cap, target):
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
        picked = rng.choice(len(names), size=6, replace=False, p=weights)
        captain_idx = picked[int(np.argmax(means[picked]))]
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
    normalized = [re.sub(r"\.\d+$", "", str(col)).strip().upper() for col in original_columns]
    roster_column_indices = []
    used = set()
    for expected in expected_slots:
        found = next(
            (i for i, name in enumerate(normalized)
             if i not in used and name == expected.upper()),
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
            if not re.search(r"\\(\\d+\\)$", str(export_df.iloc[row_idx, col_index]).strip())
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


def apply_injury_statuses(frame, key_prefix):
    """Let the user mark players Active, Questionable, or Out across all slate types."""
    if "player_injury_statuses" not in st.session_state:
        st.session_state["player_injury_statuses"] = {}
    saved_statuses = st.session_state["player_injury_statuses"]

    status_df = frame[[c for c in ["Name", "Position", "Team"] if c in frame.columns]].copy()
    status_df["Injury Status"] = status_df["Name"].astype(str).map(
        lambda name: saved_statuses.get(name.strip().casefold(), "Active")
    )
    st.write("### Player Injury Status")
    st.caption("Set each player to Active, Questionable, or Out. Players marked Out are removed from lineup building. Status choices carry across slates when the player name matches.")
    edited_statuses = st.data_editor(
        status_df,
        use_container_width=True,
        hide_index=True,
        disabled=[c for c in ["Name", "Position", "Team"] if c in status_df.columns],
        column_config={
            "Injury Status": st.column_config.SelectboxColumn(
                "Injury Status",
                options=["Active", "Questionable", "Out"],
                required=True,
                help="Choose Out to exclude the player from the player pool and lineups."
            )
        },
        key=key_prefix + "_" + str(len(status_df)) + "_" + str(status_df["Name"].astype(str).head(3).tolist())
    )
    newly_out = []
    for _, row in edited_statuses.iterrows():
        player_key = str(row["Name"]).strip().casefold()
        new_status = str(row["Injury Status"]).strip().title()
        old_status = str(saved_statuses.get(player_key, "Active")).strip().title()
        saved_statuses[player_key] = new_status
        if new_status == "Out" and old_status != "Out":
            newly_out.append(str(row["Name"]).strip())
    st.session_state["player_injury_statuses"] = saved_statuses
    # If a player is Out, clear caches only when that player's name is actually
    # present in a saved lineup/build. This also catches Out statuses saved earlier.
    out_names = {
        str(row["Name"]).strip().casefold()
        for _, row in edited_statuses.iterrows()
        if str(row["Injury Status"]).strip().casefold() == "out"
    }

    def cache_contains_out_player(value):
        if isinstance(value, pd.DataFrame):
            return any(
                value[column].astype(str).str.strip().str.casefold().isin(out_names).any()
                for column in value.columns
            )
        if isinstance(value, dict):
            return any(cache_contains_out_player(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(cache_contains_out_player(item) for item in value)
        return isinstance(value, str) and value.strip().casefold() in out_names

    cache_tokens = (
        "lineup", "portfolio", "simulation", "contest_field", "contest_results",
        "candidate", "exposure", "saved_build", "classic_pool_signature",
        "build_ready", "latest_field_ownership", "fd_active_signature",
        "fd_saved_builds", "fd_lineups"
    )
    stale_cache_found = any(
        any(token in str(key).lower() for token in cache_tokens)
        and cache_contains_out_player(value)
        for key, value in list(st.session_state.items())
    )
    if newly_out or stale_cache_found:
        # Clear every current and archived lineup/build cache so archived slate
        # state cannot restore a lineup containing an Out player.
        preserve_tokens = (
            "dropdown", "injury_status", "player_injury_statuses", "lineup_mode",
            "platform", "slate_selector"
        )
        clear_tokens = cache_tokens + ("active_slate_signature",)
        stale_build_keys = [
            key for key in list(st.session_state.keys())
            if any(token in str(key).lower() for token in clear_tokens)
            and not any(token in str(key).lower() for token in preserve_tokens)
        ]
        for key in stale_build_keys:
            st.session_state.pop(key, None)
        if newly_out:
            changed_names = newly_out
        else:
            changed_names = sorted(out_names)
        st.warning(
            "Removed saved lineups and simulations containing Out players: "
            + ", ".join(changed_names)
            + ". Build new lineups; Out players are excluded."
        )

    result = frame.copy()
    result["Injury Status"] = result["Name"].astype(str).map(
        lambda name: str(saved_statuses.get(name.strip().casefold(), "Active")).strip().title()
    )
    excluded = result[result["Injury Status"].str.casefold() == "out"]["Name"].astype(str).tolist()
    if excluded:
        st.warning("OUT players excluded from the FanDuel/DraftKings player pool and all new builds: " + ", ".join(excluded))
    result = result[result["Injury Status"].str.casefold() != "out"].reset_index(drop=True)
    if result.empty:
        st.error("All players are marked Out. Change at least one player's injury status to continue.")
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


def show_projection_refresh_status(source_files, key_prefix):
    """Show manual refresh control and the time projection files were last uploaded/refreshed."""
    import hashlib
    from datetime import datetime

    signatures = []
    for label, uploaded_file in source_files:
        if uploaded_file is None:
            signatures.append((label, None))
        else:
            digest = hashlib.sha256(uploaded_file.getvalue()).hexdigest()
            signatures.append((label, digest))

    signature_key = key_prefix + "_projection_signature"
    time_key = key_prefix + "_projection_updated_at"
    current_signature = tuple(signatures)
    if current_signature != st.session_state.get(signature_key):
        st.session_state[signature_key] = current_signature
        if any(digest is not None for _, digest in signatures):
            st.session_state[time_key] = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p %Z")

    left, right = st.columns([1, 2])
    with left:
        refresh_clicked = st.button("REFRESH PROJECTIONS", key=key_prefix + "_refresh_projections")
    with right:
        updated_at = st.session_state.get(time_key)
        if updated_at:
            st.caption("Projection files last uploaded/refreshed: " + updated_at)
        else:
            st.caption("No DFF or DraftEdge projection file uploaded yet.")

    if refresh_clicked:
        download_public_projection_table.clear()
        st.session_state[time_key] = datetime.now().astimezone().strftime("%Y-%m-%d %I:%M:%S %p %Z")
        st.success("Projection refresh requested. Uploaded CSVs take priority; public projection pages will also be checked.")
        st.rerun()


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
            if key and pd.notna(value) and np.isfinite(float(value)) and float(value) > 0:
                result[key] = float(value)
        return result
    except Exception as exc:
        st.warning(f"{source_label}: couldn't read the CSV ({exc}).")
        return {}


@st.cache_data(show_spinner=False, ttl=1800)
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
                if key and pd.notna(value) and np.isfinite(float(value)) and float(value) > 0:
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
            key = normalize_projection_player_name(row.get(name_col, ""))
            value = pd.to_numeric(
                str(row.get(proj_col, "")).replace(",", "").replace("$", ""),
                errors="coerce"
            )
            if key and pd.notna(value) and np.isfinite(float(value)) and float(value) > 0:
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
            if key and pd.notna(value) and np.isfinite(float(value)) and float(value) > 0:
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
            if key and pd.notna(value) and np.isfinite(float(value)) and float(value) > 0:
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
                        if key and pd.notna(value) and np.isfinite(float(value)) and float(value) > 0:
                            dated_result[key] = float(value)
                    if dated_result and matches_target(dated_result):
                        return dated_result
            except Exception:
                pass

    return {}

def refresh_public_projection_sources():
    """Warm all public projection downloads on app start and every 30 minutes."""
    status = {}
    for platform_name in ("DraftKings Classic", "DraftKings Showdown", "FanDuel Full Roster", "FanDuel Single Game"):
        for source_name in ("DFF", "DraftEdge"):
            loaded = bool(download_public_projection_table(source_name, platform_name))
            status[f"{source_name} ({platform_name})"] = loaded
            # Streamlit caches empty returns too; clear failed keys so the next
            # rerun can retry immediately instead of preserving a failed fetch.
            if not loaded:
                try:
                    download_public_projection_table.clear(source_name, platform_name)
                except Exception:
                    pass
    return status


@st.fragment(run_every="30m")
def automatic_projection_refresh():
    """Runs on initial page load and automatically refreshes every 30 minutes."""
    from datetime import datetime
    status = refresh_public_projection_sources()
    st.session_state["automatic_projection_refresh_time"] = datetime.now().astimezone().strftime("%Y-%m-%d %I:%M:%S %p %Z")
    st.session_state["automatic_projection_refresh_status"] = status
    successful = [name for name, loaded in status.items() if loaded]
    if successful:
        st.caption("Automatic projection downloads checked for all slate types: " + ", ".join(successful) + ". Last check: " + st.session_state["automatic_projection_refresh_time"])
    else:
        st.warning("Automatic projection download was checked, but no public projection tables could be loaded. The app will try again in 30 minutes.")


automatic_projection_refresh()


def get_projection_source_data(uploaded_file, source_name, platform_name, target_names=None):
    uploaded = read_projection_csv(uploaded_file, source_name)
    if uploaded:
        return uploaded, "uploaded CSV"
    downloaded = download_public_projection_table(source_name, platform_name, target_names=target_names)
    return downloaded, "automatic download" if downloaded else "unavailable"

def apply_external_projection_sources(players_frame, dff_file, draftedge_file, platform_name='DraftKings'):
    """Use external-site projections only for players those sites actually list."""
    result = players_frame.copy()
    target_names = result["Name"].astype(str).tolist() if "Name" in result.columns else []
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    external_available = bool(dff or draftedge)
    projections, sources = [], []
    dff_matches = draftedge_matches = averages = 0
    keep_indices = []
    for index, row in result.iterrows():
        key = normalize_projection_player_name(row.get("Name", ""))
        dff_value, edge_value = dff.get(key), draftedge.get(key)
        if dff_value is not None and edge_value is not None:
            value, source = (dff_value + edge_value) / 2.0, "DFF + DraftEdge average"
            averages += 1
        elif dff_value is not None:
            value, source = dff_value, "DFF"
        elif edge_value is not None:
            value, source = edge_value, "DraftEdge"
        elif external_available:
            # If at least one external source loaded, do not invent a projection
            # for players absent from both projection lists.
            continue
        else:
            # If both websites fail to load, keep the player row but leave its
            # projection blank; the zero/missing projection filter removes it.
            value, source = np.nan, "Not listed / source unavailable"
        keep_indices.append(index)
        projections.append(value)
        sources.append(source)
        dff_matches += int(dff_value is not None)
        draftedge_matches += int(edge_value is not None)

    result = result.loc[keep_indices].copy()
    result["Projection"] = pd.to_numeric(pd.Series(projections, index=result.index), errors="coerce")
    result["ProjectionSource"] = sources
    st.caption(
        f"Projection files matched: DFF {dff_matches} players; DraftEdge {draftedge_matches} players; "
        f"averaged {averages} players. DFF source: {dff_status}; DraftEdge source: {draftedge_status}. "
        "Players absent from both loaded projection lists are excluded; no internal projection is created for them."
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
                match = re.search(r"([A-Z]{2,3})\\s*@\\s*([A-Z]{2,3})", game_info.upper())
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


def get_contest_opponent_target(platform_key, default=20000):
    """Use selected contest field size when available; otherwise keep the existing default."""
    contest = st.session_state.get(f"selected_{platform_key}_contest") or {}
    try:
        own_entries = max(0, int(contest.get("your_entries", 0) or 0))
    except (TypeError, ValueError):
        own_entries = 0
    field_size = contest.get("field_size")
    try:
        if field_size is not None and pd.notna(field_size):
            return max(0, int(float(field_size)) - own_entries)
    except (TypeError, ValueError):
        pass
    return default


platform = st.selectbox(
    "DFS Site",
    ["DraftKings", "FanDuel"],
    key="dfs_platform"
)
mode_options = {
    "DraftKings": ["Showdown", "Classic"],
    "FanDuel": ["Single Game", "Full Roster"],
}
lineup_mode = st.selectbox(
    "Contest Type",
    mode_options[platform],
    key="lineup_mode_" + platform
)
st.subheader(platform + " " + lineup_mode)

if platform == "FanDuel":
    # FanDuel uses its own player upload and lineup rules. This separate path
    # keeps DraftKings controls and saved builds unchanged.
    st.write("### Upload FanDuel Salary File")
    st.caption(
        "Upload a FanDuel NFL player CSV. Player names, positions, salaries, "
        "and IDs are read from the file. If projections are missing, add a "
        "Projection or FPPG column for useful lineup rankings."
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
            fd_entry_file.seek(0)
            fd_entry_df = pd.read_csv(fd_entry_file)
            fd_entry_df.columns = [str(c).strip() for c in fd_entry_df.columns]
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
    st.caption(f"Simulated FanDuel opponents: {fd_opponent_target:,}")

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
        # Create a basic salary/position estimate instead of using FanDuel average fantasy points.
        fd_rate = {"QB": 2.00, "RB": 1.75, "WR": 1.70, "TE": 1.50, "K": 1.35, "DST": 1.35, "D": 1.35, "DEF": 1.35}
        fd_salary_numeric = pd.to_numeric(fd_players["Salary"], errors="coerce").fillna(0)
        fd_players["Projection"] = [
            max(0.0, (salary / 1000.0) * max(
                [fd_rate.get(pos.strip(), 1.60) for pos in str(position).split("/")],
                default=1.60
            ))
            for salary, position in zip(fd_salary_numeric, fd_players["Position"])
        ]
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
    # Remove stale saved builds as soon as an Out player is excluded.
    fd_allowed_names = set(fd_players["Name"].astype(str))
    for saved_key in list(st.session_state.get("fd_saved_builds", {}).keys()):
        saved_lineups = st.session_state["fd_saved_builds"][saved_key].get("lineups")
        if isinstance(saved_lineups, pd.DataFrame):
            lineup_columns = [c for c in saved_lineups.columns if c not in {"Salary", "ProjectedPoints", "Score"}]
            if any(saved_lineups[col].astype(str).isin(
                set(fd_raw[fd_name_col].astype(str).str.replace(r"\\s*\\(\\d+\\)\\s*$", "", regex=True)) - fd_allowed_names
            ).any() for col in lineup_columns if col in saved_lineups.columns):
                st.session_state["fd_saved_builds"].pop(saved_key, None)

    st.caption("The 5,000-lineup build automatically spreads player exposure while still favoring stronger simulated scores.")
    st.write("### Build Salary Range")
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
    fd_run_all = st.button("SIM", type="primary", use_container_width=True, key="fd_run_all_" + lineup_mode.replace(" ", "_").lower())
    if fd_run_all:
        with st.spinner("Running 10,000 FanDuel scoring simulations..."):
            rng = np.random.default_rng()
            position_rates = {
                "QB": 2.00, "RB": 1.75, "WR": 1.70, "TE": 1.50,
                "K": 1.35, "D": 1.35, "DST": 1.35, "DEF": 1.35
            }
            # FanDuel scoring differs from DraftKings: half-point receptions,
            # -2 lost fumbles, and no 300/100-yard bonuses.
            simulated_scores = np.zeros((10000, len(fd_players)), dtype=float)
            for index, (_, player_row) in enumerate(fd_players.iterrows()):
                positions = set(str(player_row["Position"]).upper().replace(" ", "").split("/"))
                n = 10000
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
                # Keep the generated outcomes unscaled; do not force them to
                # match salary-based estimates or external projections.
                simulated_scores[:, index] = np.maximum(score, 0)
        st.session_state["fd_simulation_ready_" + lineup_mode.replace(" ", "_").lower()] = True

    st.success(f"Loaded {len(fd_players)} FanDuel players after injury-status filtering.")
    if fd_proj_col is None:
        st.warning("No projection column found. All players currently have a placeholder projection of 0.01.")
    fd_player_display = fd_players.drop(columns=["FD_ID"], errors="ignore").copy()
    # Show exposure from the active FanDuel slate only.
    fd_build_key = "fd_lineups_" + lineup_mode.replace(" ", "_").lower()
    fd_current_lineups = st.session_state.get(fd_build_key)
    if isinstance(fd_current_lineups, pd.DataFrame) and not fd_current_lineups.empty:
        fd_total = len(fd_current_lineups)
        fd_slot_columns = [
            c for c in fd_current_lineups.columns
            if c.upper() in {"MVP", "FLEX", "FLEX1", "FLEX2", "FLEX3", "FLEX4",
                             "FLEX5", "QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "D"}
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

    st.dataframe(fd_player_display, use_container_width=True, hide_index=True)
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
            "FanDuel Single Game: 1 MVP (1.5x points and salary) plus 4 FLEX players. "
            "Salary cap: $60,000."
        )
        fd_slots = ["MVP", "FLEX1", "FLEX2", "FLEX3", "FLEX4"]
    else:
        st.caption(
            "FanDuel NFL Full Roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), D. "
            "Salary cap: $60,000."
        )
        fd_slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "D"]

    if fd_run_all:
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
            float(player_sim.get(name, {}).get("P95", projections[i])) * 0.50
            + float(player_sim.get(name, {}).get("P99", projections[i] * 2.3)) * 0.25
            + sim_means[i] * 0.25
            for i, name in enumerate(names)
        ], dtype=float)
        lineup_scores, fd_ownership_proxy = ownership_adjusted_player_scores(
            pool, names, np.clip(lineup_scores, 0.01, None), player_sim
        )
        eligible_sets = pool["Eligible"].tolist()
        results = []
        seen = set()
        player_build_counts = {str(name): 0 for name in names}
        target_lineups = 5000
        max_attempts = 500000
        salary_min, salary_max = int(fd_salary_range[0]), min(int(fd_salary_range[1]), 60000)
        if lineup_mode == "Single Game":
            slots = ["MVP", "FLEX1", "FLEX2", "FLEX3", "FLEX4"]
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

        for _ in range(max_attempts):
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

    if fd_run_all:
        fd_pool = fd_players.copy()
        fd_pool["Eligible"] = fd_pool["Position"].apply(
            lambda value: set(str(value).upper().replace(" ", "").split("/"))
        )
        fd_pool = fd_pool[fd_pool["Name"].isin(available_players)].copy() if "available_players" in globals() else fd_pool.copy()
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
                        for slot in ["FLEX1", "FLEX2", "FLEX3", "FLEX4"]:
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
                    st.write("### FanDuel Lineups vs. Simulated Contest Field")
                    st.caption("This is an estimate using projected points, not actual contest results.")
                    st.dataframe(compared, use_container_width=True, hide_index=True)
                    st.write("### Top Simulated Opponents")
                    st.dataframe(opponent_df.sort_values("ProjectedPoints", ascending=False).head(20), use_container_width=True, hide_index=True)
            else:
                st.error("Could not create valid FanDuel opponent lineups. Check the player pool and salary range.")

    fd_results = st.session_state.get(fd_build_key)
    if fd_results is not None:
        fd_results = remove_out_players_from_lineups(fd_results, fd_slots, "FanDuel")
        st.session_state[fd_build_key] = fd_results
        st.write(f"Built {len(fd_results)} FanDuel lineups.")
        fd_display = fd_results.copy()
        st.dataframe(fd_display, use_container_width=True, hide_index=True)

        if "FD_ID" in fd_players.columns:
            fd_ids = dict(zip(fd_players["Name"], fd_players["FD_ID"].astype(str)))
            export_slots = (
                ["MVP", "FLEX", "FLEX", "FLEX", "FLEX"]
                if lineup_mode == "Single Game"
                else ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "D"]
            )
            export_data = []
            missing_ids = []
            for _, lineup in fd_results.iterrows():
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
                st.download_button(
                    "EXPORT FANDUEL CSV",
                    export_df.to_csv(index=False).encode("utf-8"),
                    file_name=("FanDuel_Single_Game_Lineups.csv" if lineup_mode == "Single Game"
                               else "FanDuel_Full_Roster_Lineups.csv"),
                    mime="text/csv",
                    key="fd_export_" + lineup_mode.replace(" ", "_").lower()
                )
        else:
            st.info("This CSV has no player ID column, so lineup export is unavailable.")

    st.stop()

# ================================
# SETTINGS
# ================================

SIMULATIONS = 10000
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

    Projections are deliberately not used to scale simulated scores. Game scripts
    create shared game-level conditions so teammates and opponents move together.
    """
    historical = load_nfl_historical_player_stats()
    simulations = {}
    n = SIMULATIONS

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
                game_environment = np.clip(rng.normal(1.0, 0.12, n), 0.72, 1.30)
                margin = np.abs(rng.normal(0.0, 1.0, n))
                team_a_leads = rng.random(n) < 0.5
                a_leading = np.where(team_a_leads, margin, -margin)
                b_leading = -a_leading
                for side, lead_state in ((team, a_leading), (opponent, b_leading)):
                    team_scripts[side] = {
                        "scoring": np.clip(game_environment * rng.normal(1.0, 0.07, n), 0.70, 1.35),
                        "leading": lead_state > 0.35,
                        "trailing": lead_state < -0.35,
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
            name, next(iter(positions), ""), platform, historical, return_scores=True
        )
        if historical_result is not None:
            historical_points, recency_weights = historical_result
            probabilities = recency_weights / recency_weights.sum()
            scores = rng.choice(
                historical_points, size=n, replace=True, p=probabilities
            ).astype(float)

        # Use the supplied projection as a soft anchor so generic stat estimates
        # do not give low-projection bench players unrealistic averages. Keep some
        # of the sampled historical/statistical mean, and preserve the outcome
        # distribution and shared game-script variation rather than setting every
        # simulation equal to the projection.
        projection = pd.to_numeric(
            pd.Series([row.get("Projection", np.nan)]), errors="coerce"
        ).iloc[0]
        sampled_mean = float(np.mean(scores)) if len(scores) else 0.0
        if np.isfinite(projection) and projection > 0 and np.isfinite(sampled_mean) and sampled_mean > 0:
            target_mean = 0.75 * float(projection) + 0.25 * sampled_mean
            scores = scores * (target_mean / sampled_mean)

        # Shared game script adjusts the sampled outcome modestly. Trailing teams
        # throw more; leading teams lean more on their running backs.
        scoring_factor = script["scoring"]
        if position_type in ("QB", "WR", "TE"):
            script_factor = (
                scoring_factor
                + script["trailing"].astype(float) * 0.12
                - script["leading"].astype(float) * 0.06
            )
        elif position_type == "RB":
            script_factor = (
                scoring_factor
                + script["leading"].astype(float) * 0.10
                - script["trailing"].astype(float) * 0.08
            )
        elif position_type == "DST":
            script_factor = 2.0 - scoring_factor
        else:
            script_factor = scoring_factor

        script_factor = np.clip(script_factor, 0.70, 1.35)
        simulations[name] = np.maximum(scores * script_factor, 0.0)

    return pd.DataFrame(simulations)

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
        entry_file.seek(0)
        try:
            entry_df = pd.read_csv(entry_file)
        except pd.errors.ParserError:
            # Repair rows with unquoted commas in Contest Name instead of silently skipping entries.
            entry_file.seek(0)
            import csv
            import io

            entry_file.seek(0)
            try:
                raw_entry_text = entry_file.getvalue().decode("utf-8-sig", errors="replace")
                parsed_rows = list(csv.reader(io.StringIO(raw_entry_text)))
                if not parsed_rows:
                    raise ValueError("The uploaded CSV is empty.")
                header = [str(col).strip() for col in parsed_rows[0]]
                expected_fields = len(header)
                repaired_rows = []
                repaired_count = 0

                for row_number, fields in enumerate(parsed_rows[1:], start=2):
                    if not fields or all(not str(value).strip() for value in fields):
                        continue
                    if len(fields) == expected_fields:
                        repaired_rows.append(fields)
                        continue
                    if len(fields) > expected_fields and expected_fields >= 3:
                        # Only merge overflow into the contest-name column. Preserve
                        # the entry ID at column 1 and all trailing fields, including
                        # Contest ID and roster slots, in their original positions.
                        overflow = len(fields) - expected_fields
                        repaired = [
                            fields[0],
                            ",".join(str(value) for value in fields[1:2 + overflow]),
                            *fields[2 + overflow:],
                        ]
                        if len(repaired) == expected_fields:
                            repaired_rows.append(repaired)
                            repaired_count += 1
                            continue
                    raise ValueError(
                        f"CSV row {row_number} has {len(fields)} fields; expected {expected_fields}. "
                        "The app could not safely identify the missing or extra data."
                    )

                entry_df = pd.DataFrame(repaired_rows, columns=header)
            except Exception as parse_error:
                st.error(
                    "Could not safely read the DraftKings contest entry CSV. "
                    "No entries were discarded. Please check that this is the original CSV "
                    "downloaded from DraftKings My Contests. Details: "
                    f"{parse_error}"
                )
                st.stop()
            if repaired_count:
                st.warning(
                    f"Repaired {repaired_count} CSV row(s) with extra commas in contest names. "
                    "Entry IDs, contest IDs, and roster columns were kept in place. "
                    "Confirm the entry count matches DraftKings before exporting."
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

dk_opponent_target = get_contest_opponent_target("dk")
st.caption(f"Simulated DraftKings opponents: {dk_opponent_target:,}")

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
                            template_name = re.sub(r"\\s*\\(\\d+\\)\\s*$", "", template_name)
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
    for season in [2022, 2023, 2024, 2025]:
        url = f"https://github.com/nflverse/nflverse-data/releases/download/player_stats/stats_player_week_{season}.csv"
        try:
            response = requests.get(url, timeout=(8, 25))
            response.raise_for_status()
            frame = pd.read_csv(io.BytesIO(response.content), low_memory=False)
            if not frame.empty:
                frame["season"] = season
                frames.append(frame)
                loaded_seasons.append(season)
        except Exception as exc:
            errors.append(f"{season}: {exc}")
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


def _historical_player_average(player_name, position, platform, historical, return_scores=False):
    """Return recency-weighted fantasy points, or the recent weekly scores themselves."""
    if historical.empty:
        return None
    name_col = next((col for col in ["player_display_name", "player_name", "name"] if col in historical.columns), None)
    if name_col is None or "week" not in historical.columns:
        return None
    wanted = " ".join(str(player_name).casefold().replace(".", "").replace(",", "").split())
    names = historical[name_col].astype(str).str.casefold().str.replace(r"[^a-z0-9 ]", "", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    wanted = " ".join(pd.Series([wanted]).str.replace(r"[^a-z0-9 ]", "", regex=True).iloc[0].split())
    rows = historical[names == wanted].copy()
    if rows.empty:
        return None
    if "position" in rows.columns and position:
        matching = rows[rows["position"].astype(str).str.upper() == str(position).upper()]
        if not matching.empty:
            rows = matching
    if "season" in rows.columns:
        rows["season"] = pd.to_numeric(rows["season"], errors="coerce").fillna(0)
    rows["week"] = pd.to_numeric(rows["week"], errors="coerce").fillna(0)
    rows = rows.sort_values(["season", "week"]).tail(24)
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
    # More recent games count more, but older games still provide a baseline.
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

st.write("### Build Salary Range")
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

# Internal estimates fill gaps; uploaded DFF/DraftEdge projections take priority.
players_df["Projection"] = build_internal_projection_means(players_df, platform=platform)
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

internal_key = internal_slate_key(players_df)
players_df = exclude_zero_projection_players(players_df, "DraftKings " + lineup_mode)
st.caption("Projection values use the DFF/DraftEdge average when both are available, otherwise the single available source. Unmatched players use internal estimates.")
if st.session_state.get("nfl_historical_stats_status"):
    st.caption(st.session_state["nfl_historical_stats_status"])
    if st.session_state.get("nfl_historical_players_matched") is not None:
        st.caption("Historical player matches in current pool: " + str(st.session_state["nfl_historical_players_matched"]))

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

def run_game_simulations(players_df, platform="DraftKings"):
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
    return _simulate_scored_player_outcomes(eligible_players, platform, rng)

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

if "simulation_df" in st.session_state:
    simulation_df = st.session_state["simulation_df"]

    player_display["SimMean"] = simulation_df.mean(axis=0).values
    player_display["SimP10"] = simulation_df.quantile(0.10, axis=0).values
    player_display["SimP25"] = simulation_df.quantile(0.25, axis=0).values
    player_display["SimP50"] = simulation_df.quantile(0.50, axis=0).values
    player_display["SimP75"] = simulation_df.quantile(0.75, axis=0).values
    player_display["SimP90"] = simulation_df.quantile(0.90, axis=0).values
    player_display["SimP95"] = simulation_df.quantile(0.95, axis=0).values
    player_display["SimP99"] = simulation_df.quantile(0.99, axis=0).values
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

# Make the main simulated average easy to spot in the Player Pool.
# "Sim Pts" is the average fantasy score across the 10,000 simulated outcomes.
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
    "Sim P75", "Sim P90", "Sim P95", "Sim P99"
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
for setting, default in [
    ("Lock", False), ("Fade", False),
    ("Min Exposure %", 0), ("Max Exposure %", 100),
    ("Captain Min %", 0), ("Captain Max %", 100)
]:
    if existing_control_values is not None and setting in existing_control_values.columns:
        control_display[setting] = control_display["Name"].map(existing_control_values[setting]).fillna(default)
    else:
        control_display[setting] = default

st.write("### Player Controls & Exposure")
st.caption("Everything is together here. Review current exposure, then change Min/Max Exp % to guide future builds. Lock includes a player; Fade excludes a player.")
editable_control_columns = [
    "Lock", "Fade", "Min Exposure %", "Max Exposure %",
    "Captain Min %", "Captain Max %"
]
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
    "Lock", "Fade", "Min Exposure %", "Max Exposure %",
    "Captain Min %", "Captain Max %"
]:
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
                "P99": values.quantile(0.99)
            }

# Safe fallback so the page can render before the first simulation.
for _, player_row in players_df.iterrows():
    player = player_row["Name"]
    if player not in player_sim:
        projection = max(float(player_row["Projection"]), 0.01)
        player_sim[player] = {
            "Mean": projection,
            "P95": projection * 1.8,
            "P99": projection * 2.3
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

    classic_run_all = st.button("SIM", type="primary", use_container_width=True, key="dk_classic_run_all")
    if classic_run_all:
        with st.spinner("Step 1 of 3: Running 10,000 player simulations for DraftKings Classic..."):
            classic_simulation_df = run_game_simulations(players_df, platform=platform)
        st.session_state["simulation_df"] = classic_simulation_df
        st.session_state["simulations_ready"] = True

    build_clicked = classic_run_all

    if build_clicked:
        rng = np.random.default_rng()
        rankings = {}
        for _, row in classic_pool.iterrows():
            player = row["Name"]
            rankings[player] = (
                player_sim.get(player, {}).get("P95", row["Projection"]) * 0.50
                + player_sim.get(player, {}).get("P99", row["Projection"] * 2.3) * 0.25
                + player_sim.get(player, {}).get("Mean", row["Projection"]) * 0.25
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
        locked_indices = {
            i for i, name in enumerate(classic_names) if name in set(classic_locked_players)
        }
        candidate_lineups = []
        seen = set()
        classic_build_counts = {str(name): 0 for name in classic_names}
        max_attempts = 500000
        target_lineups = 5000
        for _ in range(max_attempts):
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
                expected_exposure = max(1.0, target_lineups * len(roster_slots) / max(1, len(classic_names)))
                exposure_penalty = np.asarray([
                    (1.0 + classic_build_counts.get(str(classic_names[i]), 0) / expected_exposure) ** 1.5
                    for i in choices
                ], dtype=float)
                weights /= exposure_penalty
                weights /= weights.sum()
                if rng.random() < 0.25:
                    picked = int(rng.choice(choices))
                else:
                    picked = int(rng.choice(choices, p=weights))
                chosen[slot] = str(classic_names[picked])
                used.add(picked)
                salary += int(classic_salaries[picked])
            if len(chosen) != len(roster_slots) or salary < MIN_LINEUP_SALARY or salary > MAX_LINEUP_SALARY or salary > 50000:
                continue
            if not all(name in chosen.values() for name in classic_locked_players):
                continue
            key = tuple(chosen[slot] for slot, _ in roster_slots)
            if key in seen:
                continue
            seen.add(key)
            for player_name in set(chosen.values()):
                classic_build_counts[str(player_name)] = classic_build_counts.get(str(player_name), 0) + 1
            selected_indices = [int(np.where(classic_names == chosen[slot])[0][0]) for slot, _ in roster_slots]
            projected_points = float(classic_means[selected_indices].sum())
            candidate_lineups.append({
                **chosen, "Salary": salary, "ProjectedPoints": projected_points,
                "Score": sum(rankings.get(name, 0.01) for name in chosen.values())
            })
            if len(candidate_lineups) >= target_lineups:
                break

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

    if classic_run_all:
        st.caption("Step 3 of 3: Simulating the contest field and scoring your lineups.")
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
                rows = []
                seen_contest = set()
                attempts = 0
                while len(rows) < dk_opponent_target and attempts < max(250000, dk_opponent_target * 15):
                    attempts += 1
                    chosen = {}
                    used = set()
                    salary = 0
                    for slot, eligible in contest_slots:
                        choices = pool[
                            (~pool["Name"].isin(used))
                            & pool["Eligible"].apply(lambda positions: bool(positions & eligible))
                            & ((pool["Salary"] + salary) <= MAX_LINEUP_SALARY)
                        ]
                        if choices.empty:
                            break
                        weights = choices["Weight"].to_numpy(dtype=float)
                        weights = weights / weights.sum()
                        picked = choices.iloc[int(rng.choice(len(choices), p=weights))]
                        chosen[slot] = str(picked["Name"])
                        used.add(str(picked["Name"]))
                        salary += int(picked["Salary"])
                    if len(chosen) != len(contest_slots):
                        continue
                    if salary < MIN_LINEUP_SALARY or salary > MAX_LINEUP_SALARY or salary > 50000:
                        continue
                    key = tuple(chosen[slot] for slot, _ in contest_slots)
                    if key in seen_contest:
                        continue
                    seen_contest.add(key)
                    points = sum(float(mean_scores.get(name, 0.0)) for name in chosen.values())
                    rows.append({**chosen, "Salary": salary, "ProjectedPoints": round(points, 2)})
                contest_field_df = pd.DataFrame(rows)
                user_lineups = st.session_state["classic_lineups"].copy()
                opponent_scores = contest_field_df["ProjectedPoints"].to_numpy(dtype=float) if not contest_field_df.empty else np.array([])
                if len(opponent_scores):
                    user_lineups = add_lineup_field_ownership(user_lineups)
                    user_lineups["BeatsOpponents"] = user_lineups["ProjectedPoints"].apply(lambda score: int(np.sum(opponent_scores < float(score))))
                    user_lineups["FieldPercentile"] = user_lineups["ProjectedPoints"].apply(lambda score: round(100.0 * np.mean(opponent_scores <= float(score)), 1))
                    user_lineups["FieldRank"] = user_lineups["ProjectedPoints"].apply(lambda score: 1 + int(np.sum(opponent_scores > float(score))))
                st.session_state["classic_contest_field_df"] = contest_field_df
                st.session_state["classic_contest_field_ready"] = len(contest_field_df) > 0
                st.session_state["classic_contest_comparison_df"] = user_lineups
            if not contest_field_df.empty:
                st.success(f"Compared your {len(user_lineups)} lineups against {len(contest_field_df):,} simulated opponent lineups.")
                st.write("### Your Lineups vs. Contest Field")
                st.caption("Comparison uses projected average points from the internal player simulations. It is an estimate, not actual contest results.")
                st.dataframe(user_lineups, use_container_width=True, hide_index=True)
                st.write("### Top Simulated Opponents")
                st.dataframe(contest_field_df.sort_values("ProjectedPoints", ascending=False).head(20), use_container_width=True, hide_index=True)
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
            for slot in export_slots:
                if slot in classic_display.columns:
                    classic_display[slot + " Sim Pts"] = classic_display[slot].map(
                        lambda name: round(float(classic_means.get(str(name), 0.0)), 2)
                    )
            ordered_cols = []
            for slot in export_slots:
                if slot in classic_display.columns:
                    ordered_cols.extend([slot, slot + " Sim Pts"])
            classic_display["Total Sim Pts"] = classic_display[
                [slot + " Sim Pts" for slot in export_slots if slot + " Sim Pts" in classic_display.columns]
            ].apply(pd.to_numeric, errors="coerce").sum(axis=1).round(2)
            ordered_cols.append("Total Sim Pts")
            ordered_cols.extend(c for c in classic_display.columns if c not in ordered_cols)
            classic_display = classic_display[ordered_cols]
        st.dataframe(
            classic_display,
            use_container_width=True,
            hide_index=True
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
                if entry_file is not None and selected_contest_id:
                    st.caption("Replace existing entries: preserves Entry ID and Contest ID from your DraftKings My Contests CSV.")
                    export_df = build_dk_contest_entry_export(
                        entry_df if "entry_df" in locals() else None,
                        selected_contest_id,
                        lineup_ids_df,
                        dk_upload_columns,
                        "Classic"
                    )
                    if export_df is not None:
                        st.download_button(
                            "EXPORT TO REPLACE EXISTING DK ENTRIES",
                            export_df.to_csv(index=False).encode("utf-8"),
                            file_name="DraftKings_Classic_Contest_Entries.csv",
                            mime="text/csv",
                            key="dk_classic_replace_export"
                        )
                else:
                    st.info("For an upload that replaces existing entries, upload the CSV from DraftKings My Contests above.")
                # Basic lineup export is a separate report, not a DraftKings contest-entry replacement file.
                contest_meta = st.session_state.get("selected_dk_contest", {})
                basic_export = lineup_ids_df.copy()
                basic_export.insert(0, "Contest Name", str(contest_meta.get("name", "")))
                basic_export.insert(0, "Contest ID", str(contest_meta.get("id", "")))
                st.caption("Basic export includes contest details when available, but does not target or replace existing DraftKings entries.")
                st.download_button(
                    "EXPORT BASIC CLASSIC LINEUPS (NOT ENTRY REPLACEMENT)",
                    basic_export.to_csv(index=False).encode("utf-8"),
                    file_name="DraftKings_Classic_Basic_Lineups.csv",
                    mime="text/csv",
                    key="dk_classic_basic_export"
                )
        else:
            st.info("Upload a DraftKings salary/template CSV containing player IDs to enable lineup export.")

    st.stop()


# ============================================
# BUILD LINEUPS
# ============================================

# One-click workflow: SIM runs player simulations, builds the opponent field,
# then builds and scores the user's lineups below.
build_clicked = st.button(
    "SIM",
    type="primary",
    use_container_width=False
)

# ============================================
# BUILD ACTION
# ============================================

if build_clicked:
    # One-click workflow: simulate players, build a contest field, then
    # continue below to create and score candidate lineups.
    with st.spinner("Running 10,000 game simulations..."):
        simulation_df = run_game_simulations(players_df, platform=platform)

    st.session_state["simulation_df"] = simulation_df
    st.session_state["simulations_ready"] = True
    # Build the contest field using the selected contest's field size.
    with st.spinner(f"Building {dk_opponent_target:,} simulated opponent lineups..."):
        contest_field_df = build_showdown_opponent_field(
            available_players, simulation_df, players_df, salary_map,
            captain_salary_map, SALARY_CAP, dk_opponent_target
        )
        show_field_ownership(contest_field_df, ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"], "Simulated Field Player Ownership", captain_slot="Captain")
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

    # Refresh rankings with the simulations created by this BUILD click.
    player_sim = {}
    for player in players_df["Name"]:
        values = simulation_df[player]
        player_sim[player] = {
            "Mean": values.mean(),
            "P95": values.quantile(0.95),
            "P99": values.quantile(0.99)
        }

locked_players = [
    p for p in available_players
    if control_map[p]["Lock"]
]

# ============================================
# RANK PLAYERS
# ============================================

showdown_base_scores = np.asarray([
    player_sim[p]["P95"] * 0.50
    + player_sim[p]["P99"] * 0.25
    + player_sim[p]["Mean"] * 0.25
    for p in available_players
], dtype=float)
showdown_adjusted_scores, showdown_ownership_proxy = ownership_adjusted_player_scores(
    players_df[players_df["Name"].isin(available_players)].drop_duplicates("Name"),
    available_players, showdown_base_scores, player_sim
)
showdown_rankings = {
    p: float(showdown_adjusted_scores[i]) for i, p in enumerate(available_players)
}
player_rank = sorted(available_players, key=lambda p: showdown_rankings[p], reverse=True)

# Use top players plus all locked players.
search_pool = list(dict.fromkeys(
    player_rank[:20] + locked_players
))
# Use a local generator for randomized candidate order on every slate build.
rng = np.random.default_rng()
# Shuffle candidate search order so the 5,000-lineup pool explores more flex combinations.
rng.shuffle(search_pool)

# ============================================
# ============================================
# CANDIDATE SETTINGS
# ============================================

LINEUP_COUNT = 5000
CANDIDATE_COUNT = 5000

# BUILD CANDIDATES
# ============================================

candidates = []

# Spread the 5,000 candidate lineups across eligible captains instead of
# filling the entire candidate pool with the first captain's combinations.
per_captain_candidate_limit = max(
    1,
    int(np.ceil(CANDIDATE_COUNT / max(1, len(search_pool))))
)

for captain in search_pool:
    captain_candidates = []

    if control_map[captain]["Captain Max %"] <= 0:
        continue

    flex_pool = [
        p for p in search_pool
        if p != captain
    ]

    # Sample flex groups randomly instead of taking the first combinations.
    # itertools.combinations() favors players near the start of the pool,
    # which was causing players like Allen and Stafford to appear everywhere.
    seen_flex_groups = set()
    captain_attempts = 0
    max_captain_attempts = max(1000, per_captain_candidate_limit * 40)
    while (
        len(captain_candidates) < per_captain_candidate_limit
        and captain_attempts < max_captain_attempts
        and len(flex_pool) >= 5
    ):
        captain_attempts += 1
        sampled = rng.choice(np.asarray(flex_pool, dtype=object), size=5, replace=False)
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
            total_p95 * 0.50
            + total_p99 * 0.25
            + total_mean * 0.25
        )
        lineup_ownership = (
            showdown_ownership_proxy[list(available_players).index(captain)] * 1.5
            + sum(showdown_ownership_proxy[list(available_players).index(p)] for p in flex_players)
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
    if len(candidates) >= CANDIDATE_COUNT:
        break

candidates_df = pd.DataFrame(candidates)

st.session_state["candidates_df"] = candidates_df
st.session_state["candidates_ready"] = True

st.write(
    f"Candidate lineups tested: {len(candidates_df):,}"
)


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

    lineup_cols = [
        "Captain",
        "Flex1",
        "Flex2",
        "Flex3",
        "Flex4",
        "Flex5"
    ]

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

    st.info(
        f"Candidate lineups are ready. Now scoring {n_candidates:,} lineups "
        f"against {total_field:,} simulated opponents across {n_sims:,} simulations. "
        "This step can take a while for large contests; watch the progress bar below."
    )
    scoring_status = st.empty()
    scoring_status.caption("Starting contest scoring...")

    win_rates = np.zeros(n_candidates)
    top1_rates = np.zeros(n_candidates)
    top5_rates = np.zeros(n_candidates)
    top10_rates = np.zeros(n_candidates)
    cash_rates = np.zeros(n_candidates)
    avg_percentiles = np.zeros(n_candidates)

    progress = st.progress(0)

    for sim_idx in range(n_sims):

        values = simulation_df.iloc[sim_idx].to_numpy(
            dtype=np.float32
        )

        cand_scores = (
            values[candidate_idx[:, 0]] * 1.5
            + values[candidate_idx[:, 1:]].sum(axis=1)
        )

        field_scores = (
            values[contest_idx[:, 0]] * 1.5
            + values[contest_idx[:, 1:]].sum(axis=1)
        )

        sorted_field = np.sort(field_scores)

        count_greater = (
            total_field
            - np.searchsorted(
                sorted_field,
                cand_scores,
                side="right"
            )
        )

        percentile = 1.0 - (
            count_greater / total_field
        )

        win_rates += (count_greater == 0)
        top1_rates += (percentile >= 0.99)
        top5_rates += (percentile >= 0.95)
        top10_rates += (percentile >= 0.90)
        cash_rates += (percentile >= 0.50)
        avg_percentiles += percentile

        if (sim_idx == 0 or (sim_idx + 1) % 100 == 0 or sim_idx + 1 == n_sims):
            progress.progress((sim_idx + 1) / n_sims)
            scoring_status.caption(
                f"Scoring contest: {sim_idx + 1:,} of {n_sims:,} simulations complete "
                f"({(sim_idx + 1) / n_sims:.0%})."
            )

    progress.empty()
    scoring_status.success("Contest scoring finished. Preparing your ranked lineups...")

    results_df = candidates_df.copy()

    results_df["WinRate"] = win_rates / n_sims
    results_df["Top1"] = top1_rates / n_sims
    results_df["Top5"] = top5_rates / n_sims
    results_df["Top10"] = top10_rates / n_sims
    results_df["CashRate"] = cash_rates / n_sims
    results_df["AvgPercentile"] = avg_percentiles / n_sims

    results_df["ContestScore"] = (
        results_df["Top1"] * 0.40
        + results_df["Top5"] * 0.25
        + results_df["Top10"] * 0.20
        + results_df["CashRate"] * 0.10
        + results_df["WinRate"] * 0.05
    )

    results_df = (
        results_df
        .sort_values("ContestScore", ascending=False)
        .reset_index(drop=True)
    )

    st.session_state["contest_results_df"] = results_df

# ============================================

# ============================================
# PORTFOLIO FUNCTIONS
# ============================================

PORTFOLIO_METRICS = {
    "Contest Score": "ContestScore",
    "Win %": "WinRate",
    "Top 1%": "Top1",
    "Top 5%": "Top5",
    "Top 10%": "Top10",
    "Cash %": "CashRate",
    "Average Percentile": "AvgPercentile"
}


def build_portfolio(results_df, lineup_count, metric):
    """Build a high-ranked portfolio while enforcing player exposure controls."""
    if lineup_count < 1:
        raise ValueError("Lineup count must be at least 1.")
    if metric not in results_df.columns:
        raise ValueError(f"Ranking metric not found: {metric}")

    ranked = results_df.sort_values(metric, ascending=False)
    player_counts = {}
    captain_counts = {}
    selected_rows = []
    lineup_columns = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]

    def exposure_limit(player, setting, default=100):
        settings = control_map.get(str(player), {})
        try:
            percent = float(settings.get(setting, default))
        except (TypeError, ValueError):
            percent = float(default)
        if percent <= 0:
            return 0
        return max(1, int(np.ceil(lineup_count * min(100.0, percent) / 100.0)))

    for _, row in ranked.iterrows():
        if len(selected_rows) >= lineup_count:
            break
        names = [str(row[col]) for col in lineup_columns]
        captain = str(row["Captain"])
        if any(
            player_counts.get(name, 0) >= exposure_limit(name, "Max Exposure %")
            for name in names
        ):
            continue
        if captain_counts.get(captain, 0) >= exposure_limit(captain, "Captain Max %"):
            continue
        selected_rows.append(row.copy())
        for name in set(names):
            player_counts[name] = player_counts.get(name, 0) + 1
        captain_counts[captain] = captain_counts.get(captain, 0) + 1

    if not selected_rows:
        raise ValueError(
            "No lineups fit the current exposure limits. Increase Max Exp % or Captain Max % and try again."
        )

    portfolio = pd.DataFrame(selected_rows).reset_index(drop=True)
    portfolio["Locked"] = False
    if len(portfolio) < lineup_count:
        st.warning(
            f"Exposure limits allowed {len(portfolio)} of {lineup_count} requested lineups. "
            "Raise some Max Exp % or Captain Max % limits to allow more."
        )
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
    metric
):
    """Delete one unlocked lineup and replace it with the next ranked lineup."""

    portfolio_df = portfolio_df.copy()

    if not 0 <= lineup_index < len(portfolio_df):
        return portfolio_df

    if bool(portfolio_df.loc[lineup_index, "Locked"]):
        return portfolio_df

    lineup_columns = [
        "Captain",
        "Flex1",
        "Flex2",
        "Flex3",
        "Flex4",
        "Flex5"
    ]

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

if "contest_results_df" in st.session_state:

    results_df = st.session_state["contest_results_df"]

    portfolio_count = st.number_input(
        "Number of lineups",
        min_value=1,
        max_value=min(150, len(results_df)),
        value=20,
        step=1,
        key="portfolio_count"
    )

    portfolio_metric_label = st.selectbox(
        "Rank lineups by",
        list(PORTFOLIO_METRICS.keys()),
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
        or st.session_state.get("portfolio_metric_used") != portfolio_metric
        or st.session_state.get("portfolio_control_signature") != current_control_signature
    ):

        old_portfolio = st.session_state.get("portfolio_df")

        if old_portfolio is not None and "Locked" in old_portfolio.columns:
            locked_df = old_portfolio[
                old_portfolio["Locked"] == True
            ].copy()

            available_count = max(
                0,
                int(portfolio_count) - len(locked_df)
            )

            ranked_df = (
                results_df
                .sort_values(
                    portfolio_metric,
                    ascending=False
                )
                .copy()
            )

            lineup_columns = [
                "Captain",
                "Flex1",
                "Flex2",
                "Flex3",
                "Flex4",
                "Flex5"
            ]

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

            portfolio_df = build_portfolio(
                results_df,
                int(portfolio_count),
                portfolio_metric
            )

        st.session_state["portfolio_df"] = portfolio_df
        st.session_state["portfolio_count_used"] = portfolio_count
        st.session_state["portfolio_metric_used"] = portfolio_metric
        st.session_state["portfolio_control_signature"] = current_control_signature

    portfolio_df = st.session_state["portfolio_df"].copy()
    portfolio_df = add_lineup_field_ownership(portfolio_df)

    # Add each lineup's total salary to the portfolio display and export.
    portfolio_df["Salary"] = portfolio_df.apply(
        lambda row: int(
            captain_salary_map.get(str(row["Captain"]), 0)
            + sum(
                salary_map.get(str(row[col]), 0)
                for col in ["Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
            )
        ),
        axis=1
    )
    st.session_state["portfolio_df"] = portfolio_df

    # Show each rostered player's average score across the player simulations.
    # For the Showdown captain, apply the 1.5x scoring multiplier.
    sim_scores = st.session_state.get("simulation_df")
    if isinstance(sim_scores, pd.DataFrame) and not sim_scores.empty:
        sim_player_means = sim_scores.mean(axis=0, numeric_only=True).to_dict()
        for slot in ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]:
            if slot not in portfolio_df.columns:
                continue
            multiplier = 1.5 if slot == "Captain" else 1.0
            score_col = slot + " Sim Pts"
            portfolio_df[score_col] = portfolio_df[slot].map(
                lambda player: round(float(sim_player_means.get(str(player), 0.0)) * multiplier, 2)
            )
        sim_point_columns = [
            slot + " Sim Pts"
            for slot in ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
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

    display_columns = [
        "Captain",
        "Captain Sim Pts",
        "Flex1",
        "Flex1 Sim Pts",
        "Flex2",
        "Flex2 Sim Pts",
        "Flex3",
        "Flex3 Sim Pts",
        "Flex4",
        "Flex4 Sim Pts",
        "Flex5",
        "Flex5 Sim Pts",
        "Total Sim Pts",
        "Lineup Ownership Score (%)",
        "Salary",
        "ContestScore",
        "WinRate",
        "Top1",
        "Top5",
        "Top10",
        "CashRate",
        "Locked"
    ]

    display_df = portfolio_df[
        [c for c in display_columns if c in portfolio_df.columns]
    ].copy()

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

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # Show realized exposure in the final portfolio after Contest Sim.
    lineup_columns = [
        col for col in ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        if col in portfolio_df.columns
    ]
    captain_count = (
        portfolio_df["Captain"].value_counts()
        if "Captain" in portfolio_df.columns else pd.Series(dtype=int)
    )
    total_lineups = len(portfolio_df)
    exposure_rows = []
    if total_lineups:
        for _, player_row in players_df.iterrows():
            player_name = str(player_row["Name"])
            appearances = sum(
                (portfolio_df[col].astype(str) == player_name).sum()
                for col in lineup_columns
            )
            captain_appearances = int(captain_count.get(player_name, 0))
            if appearances:
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
        st.dataframe(exposure_df, use_container_width=True, hide_index=True)
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
        "Top10", "CashRate"
    ]
    portfolio_df = remove_out_players_from_lineups(
        portfolio_df,
        ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5", "QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST", "MVP", "D"],
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

    st.write("### Portfolio Controls")

    for idx in portfolio_df.index:

        cols = st.columns([0.7, 1.0, 1.0])

        cols[0].write(f"Lineup {idx + 1}")

        if bool(portfolio_df.loc[idx, "Locked"]):
            cols[1].success("LOCKED")
        else:
            if cols[1].button(
                "LOCK",
                key=f"portfolio_lock_{idx}"
            ):
                portfolio_df = lock_portfolio_lineup(
                    portfolio_df,
                    idx
                )

                st.session_state["portfolio_df"] = portfolio_df
                st.rerun()

        if bool(portfolio_df.loc[idx, "Locked"]):
            cols[2].write("Protected")
        else:
            if cols[2].button(
                "DELETE",
                key=f"portfolio_delete_{idx}"
            ):
                portfolio_df = delete_and_replace_portfolio_lineup(
                    portfolio_df,
                    results_df,
                    idx,
                    portfolio_metric
                )

                st.session_state["portfolio_df"] = portfolio_df
                st.rerun()

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
                    st.caption("This export replaces your existing contest entries and preserves their Entry IDs and Contest ID.")
                    export_df = build_dk_contest_entry_export(
                        entry_df,
                        selected_contest_id,
                        lineup_ids_df,
                        showdown_slots,
                        "Showdown"
                    )
                    if export_df is not None:
                        st.download_button(
                            label="EXPORT SHOWDOWN LINEUPS",
                            data=export_df.to_csv(index=False).encode("utf-8"),
                            file_name="DraftKings_Showdown_Contest_Entries.csv",
                            mime="text/csv",
                            use_container_width=True,
                            key="dk_showdown_unified_export"
                        )
                else:
                    # This roster-only file is for uploading lineups as new entries.
                    # Replacing existing entries requires the DraftKings My Contests CSV.
                    basic_export = lineup_ids_df.copy()
                    st.warning(
                        "BASIC LINEUP FILE ONLY: This file contains player IDs, but no contest or entry IDs. "
                        "It will NOT replace your existing contest entries. To replace those entries, upload "
                        "your DraftKings My Contests CSV and select the contest first."
                    )
                    st.download_button(
                        label="EXPORT BASIC LINEUPS — NEW ENTRIES ONLY",
                        data=basic_export.to_csv(index=False).encode("utf-8"),
                        file_name="DraftKings_Showdown_Lineups.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="dk_showdown_unified_export"
                    )
                st.link_button(
                    "UPLOAD TO DRAFTKINGS",
                    "https://www.draftkings.com/lineup/upload",
                    use_container_width=True
                )
    else:
        st.info("Run CONTEST SIM and build your final portfolio first.")
