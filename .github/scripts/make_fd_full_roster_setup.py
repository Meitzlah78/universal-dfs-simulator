from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# Match the DK Classic field method: build opponent weights and lineup strength
# from the mean of the actual player simulations, not raw projections alone.
needle = '''            fd_pool["Projection"] = pd.to_numeric(fd_pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01)
            fd_weights = opponent_field_selection_weights(
                fd_pool, fd_pool["Projection"].to_numpy(dtype=float)
            )
            fd_weights = fd_weights / fd_weights.sum() if fd_weights.sum() else np.full(len(fd_pool), 1 / max(len(fd_pool), 1))
'''
replacement = '''            fd_pool["Projection"] = pd.to_numeric(fd_pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01)
            fd_sim_df = st.session_state.get("simulation_df")
            if isinstance(fd_sim_df, pd.DataFrame) and not fd_sim_df.empty:
                fd_mean_scores = fd_sim_df.mean(axis=0).to_dict()
            else:
                fd_mean_scores = {}
            fd_pool["MeanPoints"] = fd_pool["Name"].map(fd_mean_scores).fillna(fd_pool["Projection"])
            fd_weights = opponent_field_selection_weights(
                fd_pool, fd_pool["MeanPoints"].to_numpy(dtype=float)
            )
            fd_weights = fd_weights / fd_weights.sum() if fd_weights.sum() else np.full(len(fd_pool), 1 / max(len(fd_pool), 1))
'''
if needle not in text:
    raise SystemExit("FanDuel opponent weighting block not found")
text = text.replace(needle, replacement, 1)

needle2 = '''                                fd_field_projections = pd.to_numeric(fd_pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01).to_numpy(dtype=float)
'''
replacement2 = '''                                fd_field_projections = pd.to_numeric(fd_pool["MeanPoints"], errors="coerce").fillna(fd_pool["Projection"]).fillna(0.01).clip(lower=0.01).to_numpy(dtype=float)
'''
if needle2 not in text:
    raise SystemExit("FanDuel cached field scoring block not found")
text = text.replace(needle2, replacement2, 1)

path.write_text(text, encoding="utf-8")
