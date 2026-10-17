from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''            classic_names = classic_pool["Name"].astype(str).to_numpy(dtype=object)\n            classic_salaries = pd.to_numeric(classic_pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)\n            classic_eligible = classic_pool["Eligible"].tolist()\n'''
new = '''            classic_names = classic_pool["Name"].astype(str).to_numpy(dtype=object)\n            classic_salaries = pd.to_numeric(classic_pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)\n            classic_eligible = classic_pool["Eligible"].tolist()\n            # Hot-loop metadata: keep pandas row lookups out of the bounded builder.\n            classic_teams = classic_pool.get("Team", pd.Series("", index=classic_pool.index)).fillna("").astype(str).str.strip().str.upper().to_numpy(dtype=object)\n            classic_opponents = classic_pool.get("Opponent", pd.Series("", index=classic_pool.index)).fillna("").astype(str).str.strip().str.upper().to_numpy(dtype=object)\n            classic_positions = classic_pool.get("Position", pd.Series("", index=classic_pool.index)).fillna("").astype(str).str.upper().str.split("/").str[0].to_numpy(dtype=object)\n'''
if old not in text:
    raise SystemExit("classic metadata anchor not found")
text = text.replace(old, new, 1)

old = '''                    choices = np.asarray([\n                        i for i in eligible_indices[slot]\n                        if i not in used and salary + classic_salaries[i] <= MAX_LINEUP_SALARY\n                    ], dtype=int)\n'''
new = '''                    base_choices = eligible_indices[slot]\n                    if used:\n                        used_mask = ~np.isin(base_choices, np.fromiter(used, dtype=int, count=len(used)))\n                    else:\n                        used_mask = np.ones(len(base_choices), dtype=bool)\n                    salary_mask = salary + classic_salaries[base_choices] <= MAX_LINEUP_SALARY\n                    choices = base_choices[used_mask & salary_mask]\n'''
if old not in text:
    raise SystemExit("classic choices anchor not found")
text = text.replace(old, new, 1)

old = '''                        qb_matches = np.flatnonzero(classic_names == qb_name)\n                        if len(qb_matches):\n                            qb_i = int(qb_matches[0])\n                            qb_team = str(classic_pool.iloc[qb_i].get("Team", "")).strip().upper()\n                            qb_opp = str(classic_pool.iloc[qb_i].get("Opponent", "")).strip().upper()\n'''
new = '''                        qb_i = name_to_index.get(qb_name)\n                        if qb_i is not None:\n                            qb_team = str(classic_teams[qb_i])\n                            qb_opp = str(classic_opponents[qb_i])\n'''
if old not in text:
    raise SystemExit("classic qb lookup anchor not found")
text = text.replace(old, new, 1)

old = '''                                hits = np.flatnonzero(classic_names == str(picked_name))\n                                if not len(hits):\n                                    continue\n                                row = classic_pool.iloc[int(hits[0])]\n                                pos = str(row.get("Position", "")).upper().split("/")[0]\n                                if pos not in {"RB", "WR", "TE"}:\n                                    continue\n                                team = str(row.get("Team", "")).strip().upper()\n'''
new = '''                                picked_i = name_to_index.get(str(picked_name))\n                                if picked_i is None:\n                                    continue\n                                pos = str(classic_positions[picked_i])\n                                if pos not in {"RB", "WR", "TE"}:\n                                    continue\n                                team = str(classic_teams[picked_i])\n'''
if old not in text:
    raise SystemExit("classic picked-player lookup anchor not found")
text = text.replace(old, new, 1)

old = '''                                forced = [i for i in choices if str(classic_pool.iloc[i].get("Team", "")).strip().upper() == qb_team]\n                            elif need_bring and bring_now < 1 and skill_slots_left <= 1:\n                                forced = [i for i in choices if str(classic_pool.iloc[i].get("Team", "")).strip().upper() == qb_opp]\n'''
new = '''                                forced = choices[classic_teams[choices] == qb_team]\n                            elif need_bring and bring_now < 1 and skill_slots_left <= 1:\n                                forced = choices[classic_teams[choices] == qb_opp]\n'''
if old not in text:
    raise SystemExit("classic forced-team anchor not found")
text = text.replace(old, new, 1)

old = '''                            if forced:\n                                mask = np.isin(choices, np.asarray(forced, dtype=int))\n'''
new = '''                            if len(forced):\n                                mask = np.isin(choices, np.asarray(forced, dtype=int))\n'''
if old not in text:
    raise SystemExit("classic forced truthiness anchor not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Installed vectorized DK Classic hot-loop builder optimizations")
