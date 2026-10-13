from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

MARKER = "# FanDuel Single Game role weights: MVP and FLEX are modeled separately."

if MARKER not in text:
    old = '''            fd_weights = opponent_field_selection_weights(
                fd_pool, fd_pool["Projection"].to_numpy(dtype=float)
            )
            fd_weights = fd_weights / fd_weights.sum() if fd_weights.sum() else np.full(len(fd_pool), 1 / max(len(fd_pool), 1))
            rng = np.random.default_rng(123)
'''
    new = '''            fd_weights = opponent_field_selection_weights(
                fd_pool, fd_pool["Projection"].to_numpy(dtype=float)
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
'''
    if old not in text:
        raise SystemExit("FanDuel field-weight anchor not found")
    text = text.replace(old, new, 1)

old_mvp = '''                            mvp_weights = mvp_candidates["Projection"].to_numpy(dtype=float)
                            mvp_weights = mvp_weights / mvp_weights.sum()
                            mvp_row = mvp_candidates.iloc[int(rng.choice(len(mvp_candidates), p=mvp_weights))]
'''
new_mvp = '''                            mvp_candidate_indices = mvp_candidates.index.to_numpy(dtype=int)
                            mvp_weights = np.clip(fd_mvp_weights[mvp_candidate_indices].astype(float), 0.01, None)
                            mvp_weights = mvp_weights / mvp_weights.sum()
                            mvp_row = mvp_candidates.iloc[int(rng.choice(len(mvp_candidates), p=mvp_weights))]
'''
if old_mvp in text:
    text = text.replace(old_mvp, new_mvp, 1)
elif new_mvp not in text:
    raise SystemExit("FanDuel MVP selection anchor not found")

old_flex = '''                                weights = fd_weights[choice_indices].astype(float)
                                weights = weights / weights.sum() if weights.sum() else np.full(len(choices), 1.0 / len(choices))
'''
new_flex = '''                                weights = fd_flex_weights[choice_indices].astype(float)
                                weights = weights / weights.sum() if weights.sum() else np.full(len(choices), 1.0 / len(choices))
'''
if old_flex in text:
    text = text.replace(old_flex, new_flex, 1)
elif new_flex not in text:
    raise SystemExit("FanDuel FLEX selection anchor not found")

APP.write_text(text, encoding="utf-8")
print("FanDuel Single Game now uses separate MVP and FLEX ownership weights.")
