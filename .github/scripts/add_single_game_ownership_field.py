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


replace_once(
'''    names = np.asarray(list(available_players), dtype=object)
    means = simulation_df.mean(axis=0).reindex(names).fillna(0.01).to_numpy(dtype=float)
    weights = np.clip(means, 0.01, None)
    weights /= weights.sum()
''',
'''    names = np.asarray(list(available_players), dtype=object)
    means = simulation_df.mean(axis=0).reindex(names).fillna(0.01).to_numpy(dtype=float)

    # Opponent construction is ownership-first. Projection/sim strength is only
    # the fallback before a usable ownership estimate exists for the slate.
    ownership_pool = players_df.drop_duplicates("Name", keep="first").set_index("Name").reindex(names).reset_index()
    weights = opponent_field_selection_weights(ownership_pool, means)
    weights = np.clip(weights, 0.01, None)
    weights /= weights.sum()

    cpt_lookup = {str(c).strip().casefold(): c for c in ownership_pool.columns}
    cpt_col = next((cpt_lookup[k] for k in (
        "field cpt own %", "field captain own %", "captain ownership %", "cpt ownership %"
    ) if k in cpt_lookup), None)
    if cpt_col is not None:
        captain_base_weights = pd.to_numeric(ownership_pool[cpt_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        if captain_base_weights.sum() <= 0:
            captain_base_weights = weights.copy()
    else:
        captain_base_weights = weights.copy()
''',
"showdown ownership-first base weights",
)

replace_once(
'''        # Randomize Captain assignment among the six selected players, weighted by projection.
        # Choosing the highest-projection player every time incorrectly makes the top-projected
        # player Captain in every lineup where they appear, inflating Captain ownership to overall ownership.
        captain_weights = np.clip(means[picked], 0.01, None)
''',
'''        # Captain selection uses Captain ownership when available; otherwise it
        # falls back to the same ownership-first overall field weights.
        captain_weights = np.clip(captain_base_weights[picked], 0.01, None)
''',
"showdown captain ownership weights",
)

APP.write_text(text, encoding="utf-8")
print("Patched ownership-first single-game opponent construction")
