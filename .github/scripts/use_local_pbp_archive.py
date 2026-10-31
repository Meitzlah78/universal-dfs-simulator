from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

start = text.find('@st.cache_data(show_spinner=False, ttl=86400)\ndef _download_nfl_pbp_game_history():')
end = text.find('\ndef build_historical_volatility_check(', start)
if start < 0 or end < 0:
    raise SystemExit("Could not locate the shared PBP loader block")

new_block = r'''@st.cache_data(show_spinner=False, ttl=86400)
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

'''

text = text[:start] + new_block + text[end:]
APP.write_text(text, encoding="utf-8")
print("Patched PBP loader to prefer repo archives before nflverse")
