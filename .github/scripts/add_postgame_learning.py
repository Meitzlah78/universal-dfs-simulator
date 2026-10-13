from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch anchor not found: {label}")
    text = text.replace(old, new, 1)


# 1) Save field ownership separately for each format so snapshots do not mix slates.
replace_once(
'''def show_field_ownership(field_df, slots, title, captain_slot=None):
    ownership_df = calculate_field_ownership(field_df, slots, captain_slot)
    st.session_state["latest_field_ownership"] = ownership_df
    if not ownership_df.empty:
''',
'''def show_field_ownership(field_df, slots, title, captain_slot=None):
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
''',
"format-specific ownership cache",
)

# 2) Add automatic snapshot helpers before the format selector.
replace_once(
'''    return default


format_options = {
''',
'''    return default


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
    snapshot.insert(0, "GameDate", game_date)
    snapshot.insert(1, "Format", str(format_label))
    snapshot.insert(2, "Snapshot Saved ET", now.strftime("%Y-%m-%d %I:%M:%S %p ET"))
    snapshot["Contest ID"] = str(contest.get("id", "") or "")
    snapshot["Contest Name"] = str(contest.get("name", "") or "")
    snapshot["Entry Fee ($)"] = pd.to_numeric(contest.get("entry_fee"), errors="coerce")
    snapshot["Field Size"] = pd.to_numeric(contest.get("field_size"), errors="coerce")
    snapshot["Your Entries"] = pd.to_numeric(contest.get("your_entries"), errors="coerce")
    snapshot["Game Correlation %"] = round(float(correlation_pct), 1)
    snapshot["Build Aggressiveness %"] = round(float(aggressiveness_pct), 1)

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
''',
"snapshot helper functions",
)

# 3) DraftKings automatic snapshot: save after SIM data exists.
replace_once(
'''    st.caption("Player stats, simulation results, exposure, and editable controls are all in this one table. Lock includes a player; Fade excludes a player.")
''',
'''    if isinstance(st.session_state.get("simulation_df"), pd.DataFrame) and not st.session_state["simulation_df"].empty:
        save_automatic_pregame_snapshot(
            control_display,
            selected_format,
            correlation_pct=float(correlation_strength) * 100.0,
            aggressiveness_pct=float(aggressiveness) * 100.0,
        )

    st.caption("Player stats, simulation results, exposure, and editable controls are all in this one table. Lock includes a player; Fade excludes a player.")
''',
"DK automatic snapshot",
)

# 4) Make the old manual snapshot clearly a backup only.
replace_once(
'''        st.caption(
            "Download this before kickoff. After the game, add an ActualPoints column "
            "with each player's fantasy points, then upload the file in Projection Accuracy Report."
        )
''',
'''        st.caption(
            "The app now automatically saves the latest pregame snapshot after SIM. "
            "This download is only an extra backup copy."
        )
''',
"snapshot caption",
)

# 5) FanDuel automatic snapshot after a successful simulation.
replace_once(
'''        st.dataframe(
            fd_player_display,
            use_container_width=True,
            hide_index=True,
            column_config={"Name": st.column_config.TextColumn("Name", pinned=True)},
        )
''',
'''        fd_snapshot_display = fd_player_display.copy()
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

        st.dataframe(
            fd_player_display,
            use_container_width=True,
            hide_index=True,
            column_config={"Name": st.column_config.TextColumn("Name", pinned=True)},
        )
''',
"FD automatic snapshot",
)

# 6) One-file post-game learner immediately before the existing ROI tracker.
replace_once(
'''# ============================================
# SIMMAH ROI TRACKER
''',
'''# ============================================
# POST-GAME LEARNING
# ============================================
with st.expander("Post-Game Learning — Completed Contest CSV", expanded=False):
    st.caption(
        "Upload the completed contest standings CSV. The app compares actual scores, ownership, "
        "CPT/MVP ownership, duplicates, and your finishes with the automatically saved pregame snapshot."
    )
    completed_contest_file = st.file_uploader(
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
                    normalized = entries[lineup_col].fillna("").astype(str).str.replace(r"\\s+", " ", regex=True).str.strip()
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
                    st.dataframe(comparison[show_cols], use_container_width=True, hide_index=True)

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
''',
"post-game learning UI",
)

APP.write_text(text, encoding="utf-8")
print("Patched dfs_app.py")
