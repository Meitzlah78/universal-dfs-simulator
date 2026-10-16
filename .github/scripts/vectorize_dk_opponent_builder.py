from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()
start = text.index("def build_showdown_opponent_field(")
end = text.index("\n\n\ndef expand_showdown_field_by_ownership", start)
old = text[start:end]
if "while len(rows) < target and attempts < max_attempts:" not in old:
    raise SystemExit("SAFE_ABORT: expected legacy opponent loop not found")

new = '''def build_showdown_opponent_field(available_players, simulation_df, players_df,
                                  salary_map, captain_salary_map, salary_cap, target,
                                  progress_bar=None, progress_text=None):
    """Build Showdown opponents in NumPy batches instead of one lineup at a time."""
    columns = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5", "Salary"]
    target = int(target)
    if target <= 0 or len(available_players) < 6:
        return pd.DataFrame(columns=columns)

    names = np.asarray(list(available_players), dtype=object)
    means = simulation_df.mean(axis=0).reindex(names).fillna(0.01).to_numpy(dtype=float)
    ownership_pool = players_df.drop_duplicates("Name", keep="first").set_index("Name").reindex(names).reset_index()
    weights = np.asarray(opponent_field_selection_weights(ownership_pool, means), dtype=np.float64)
    weights = np.clip(weights, 0.01, None)
    weights /= weights.sum()

    cpt_lookup = {str(c).strip().casefold(): c for c in ownership_pool.columns}
    cpt_col = next((cpt_lookup[k] for k in (
        "field cpt own %", "field captain own %", "captain ownership %", "cpt ownership %"
    ) if k in cpt_lookup), None)
    if cpt_col is not None:
        captain_weights = pd.to_numeric(ownership_pool[cpt_col], errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
        if captain_weights.sum() <= 0:
            captain_weights = weights.copy()
    else:
        captain_weights = weights.copy()
    captain_weights = np.clip(captain_weights, 0.01, None)
    captain_weights /= captain_weights.sum()

    salaries = np.asarray([int(salary_map.get(name, 0)) for name in names], dtype=np.int64)
    captain_salaries = np.asarray([int(captain_salary_map.get(name, salary_map.get(name, 0))) for name in names], dtype=np.int64)
    team_lookup = players_df.drop_duplicates("Name").set_index("Name")["Team"].to_dict()
    team_labels = np.asarray([str(team_lookup.get(name, "")) for name in names], dtype=object)
    _, team_codes = np.unique(team_labels, return_inverse=True)

    rng = np.random.default_rng(123)
    accepted = []
    attempts = 0
    max_attempts = max(200000, target * 10)
    # Generate many constructions per Python iteration.  Weighted Gumbel-top-k
    # samples five FLEX players without replacement and avoids a Python rng.choice
    # call for every lineup.
    log_flex_weights = np.log(weights)
    batch_size = min(8192, max(1024, target))

    while sum(len(batch) for batch in accepted) < target and attempts < max_attempts:
        remaining_attempts = max_attempts - attempts
        current_batch = min(batch_size, remaining_attempts)
        captain_idx = rng.choice(len(names), size=current_batch, p=captain_weights)

        gumbels = rng.gumbel(size=(current_batch, len(names)))
        flex_scores = gumbels + log_flex_weights[None, :]
        flex_scores[np.arange(current_batch), captain_idx] = -np.inf
        flex_idx = np.argpartition(flex_scores, -5, axis=1)[:, -5:]

        lineup_salary = captain_salaries[captain_idx] + salaries[flex_idx].sum(axis=1)
        salary_ok = (lineup_salary <= int(salary_cap)) & (lineup_salary >= 49000)
        captain_team = team_codes[captain_idx]
        flex_teams = team_codes[flex_idx]
        multi_team = np.any(flex_teams != captain_team[:, None], axis=1)
        valid = np.flatnonzero(salary_ok & multi_team)
        if len(valid):
            accepted.append(np.column_stack((
                captain_idx[valid], flex_idx[valid], lineup_salary[valid]
            )))
        attempts += current_batch

        accepted_count = sum(len(batch) for batch in accepted)
        if progress_bar is not None:
            progress_bar.progress(
                min(0.99, attempts / max_attempts),
                text=f"Building opponent lineups: {min(accepted_count, target):,} of {target:,} accepted (attempt {attempts:,})"
            )

    if not accepted:
        return pd.DataFrame(columns=columns)
    matrix = np.vstack(accepted)[:target]
    player_indices = matrix[:, :6].astype(np.int64, copy=False)
    rows = np.empty((len(matrix), 7), dtype=object)
    rows[:, :6] = names[player_indices]
    rows[:, 6] = matrix[:, 6].astype(np.int64, copy=False)
    if progress_bar is not None:
        progress_bar.progress(1.0, text=f"Building opponent lineups: {len(rows):,} of {target:,} accepted")
    return pd.DataFrame(rows, columns=columns)
'''
text = text[:start] + new + text[end:]
path.write_text(text)
