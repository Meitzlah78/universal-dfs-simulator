from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old_columns = '''    wanted_columns = {
        "season", "week", "game_id", "play_id", "play_type", "total_home_score",
        "total_away_score", "game_seconds_remaining", "qtr"
    }
'''
new_columns = '''    wanted_columns = {
        "season", "week", "game_id", "play_id", "play_type", "total_home_score",
        "total_away_score", "game_seconds_remaining", "qtr",
        # Keep successful 2PT result data in the shared PBP history so the
        # game-environment layer can learn conversion frequency without any
        # DraftKings/FanDuel-specific scoring logic.
        "two_point_conv_result",
    }
'''
if new_columns not in text:
    if old_columns not in text:
        raise SystemExit("PBP wanted_columns anchor not found")
    text = text.replace(old_columns, new_columns, 1)

old_counts = '''        play_counts = work.groupby("game_id").agg(
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
'''
new_counts = '''        play_counts = work.groupby("game_id").agg(
            GamePlays=("play_id", "count"),
            PassPlays=("play_type", lambda values: values.astype(str).str.lower().eq("pass").sum()),
            RunPlays=("play_type", lambda values: values.astype(str).str.lower().eq("run").sum()),
        ).reset_index()
        if "two_point_conv_result" in work.columns:
            # nflverse marks successful conversions as "success". Failed or
            # missing attempts contribute zero; scoring attribution remains in
            # the shared player-stat layer rather than in this site-neutral PBP summary.
            result = work["two_point_conv_result"].astype(str).str.strip().str.lower()
            work["_two_point_success"] = result.eq("success").astype(int)
            two_point_counts = work.groupby("game_id")["_two_point_success"].sum().rename("TwoPointConversions").reset_index()
            play_counts = play_counts.merge(two_point_counts, on="game_id", how="left")
        else:
            play_counts["TwoPointConversions"] = 0
        final_scores = final_scores.merge(play_counts, on="game_id", how="left")
        final_scores[["GamePlays", "PassPlays", "RunPlays", "TwoPointConversions"]] = (
            final_scores[["GamePlays", "PassPlays", "RunPlays", "TwoPointConversions"]].fillna(0)
        )
        final_scores["season"] = pd.to_numeric(final_scores["season"], errors="coerce")
        return final_scores[
            ["season", "game_id", "GamePoints", "GamePlays", "PassPlays", "RunPlays", "TwoPointConversions"]
        ]
'''
if new_counts not in text:
    if old_counts not in text:
        raise SystemExit("PBP summary anchor not found")
    text = text.replace(old_counts, new_counts, 1)

old_empty = '''    history = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["season", "game_id", "GamePoints", "GamePlays", "PassPlays", "RunPlays"]
    )
'''
new_empty = '''    history = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["season", "game_id", "GamePoints", "GamePlays", "PassPlays", "RunPlays", "TwoPointConversions"]
    )
'''
if new_empty not in text:
    if old_empty not in text:
        raise SystemExit("PBP empty-history anchor not found")
    text = text.replace(old_empty, new_empty, 1)

path.write_text(text)
