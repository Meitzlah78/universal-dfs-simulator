from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# Replace repeated DataFrame filtering in every roster slot with precomputed NumPy arrays.
needle = '''                        else:
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
'''
replacement = '''                        else:
                            roster = [
                                ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                                ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                                ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}),
                                ("D", {"D", "DST", "DEF"})
                            ]
                            # Cache these once per field build instead of scanning the
                            # whole DataFrame nine times for every attempted lineup.
                            if "fd_full_field_cache" not in locals():
                                fd_field_names = fd_pool["Name"].astype(str).to_numpy()
                                fd_field_salaries = pd.to_numeric(fd_pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=int)
                                fd_field_projections = pd.to_numeric(fd_pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01).to_numpy(dtype=float)
                                fd_field_positions = fd_pool["Eligible"].tolist()
                                fd_full_field_cache = {
                                    slot: np.asarray([
                                        i for i, positions in enumerate(fd_field_positions)
                                        if bool(positions & eligible)
                                    ], dtype=int)
                                    for slot, eligible in roster
                                }
                                fd_field_slot_bounds = {
                                    slot: (
                                        int(fd_field_salaries[idxs].min()),
                                        int(fd_field_salaries[idxs].max())
                                    )
                                    for slot, idxs in fd_full_field_cache.items() if len(idxs)
                                }
                            used_indices = set()
                            for roster_pos, (slot, eligible) in enumerate(roster):
                                choices = fd_full_field_cache.get(slot, np.asarray([], dtype=int))
                                if used_indices:
                                    choices = choices[~np.isin(choices, np.fromiter(used_indices, dtype=int))]
                                if not len(choices):
                                    break
                                remaining_roster = roster[roster_pos + 1:]
                                if remaining_roster:
                                    if any(s not in fd_field_slot_bounds for s, _ in remaining_roster):
                                        choices = np.asarray([], dtype=int)
                                    else:
                                        min_remaining = sum(fd_field_slot_bounds[s][0] for s, _ in remaining_roster)
                                        max_remaining = sum(fd_field_slot_bounds[s][1] for s, _ in remaining_roster)
                                        candidate_salary = salary + fd_field_salaries[choices]
                                        feasible = (
                                            (candidate_salary + max_remaining >= fd_salary_range[0])
                                            & (candidate_salary + min_remaining <= min(fd_salary_range[1], 60000))
                                        )
                                        choices = choices[feasible]
                                else:
                                    candidate_salary = salary + fd_field_salaries[choices]
                                    choices = choices[
                                        (candidate_salary >= fd_salary_range[0])
                                        & (candidate_salary <= min(fd_salary_range[1], 60000))
                                    ]
                                if not len(choices):
                                    break
                                weights = np.clip(fd_weights[choices].astype(float), 0.0001, None)
                                weights /= weights.sum()
                                picked_idx = int(rng.choice(choices, p=weights))
                                name = str(fd_field_names[picked_idx])
                                chosen[slot] = name
                                used.add(name)
                                used_indices.add(picked_idx)
                                salary += int(fd_field_salaries[picked_idx])
                                points += float(fd_field_projections[picked_idx])
'''
if needle not in text:
    raise SystemExit("FanDuel Full Roster opponent builder block not found")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
