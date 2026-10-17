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


# Current Full Roster already precomputes slot eligibility and salary bounds.
# Optimize only remaining hot-loop work without changing roster or sim rules.
replace_once(
'''        names = pool["Name"].astype(str).to_numpy(dtype=object)
        salaries = pd.to_numeric(pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
        projections = pd.to_numeric(pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01).to_numpy(dtype=float)
''',
'''        names = pool["Name"].astype(str).to_numpy(dtype=object)
        salaries = pd.to_numeric(pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
        fd_build_teams = pool.get("Team", pd.Series("", index=pool.index)).fillna("").astype(str).str.strip().str.upper().to_numpy(dtype=object)
        fd_build_opponents = pool.get("Opponent", pd.Series("", index=pool.index)).fillna("").astype(str).str.strip().str.upper().to_numpy(dtype=object)
        fd_build_positions = pool.get("Position", pd.Series("", index=pool.index)).fillna("").astype(str).str.upper().str.replace(" ", "", regex=False).str.split("/").str[0].to_numpy(dtype=object)
        fd_build_name_to_index = {str(name): i for i, name in enumerate(names)}
        projections = pd.to_numeric(pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01).to_numpy(dtype=float)
''',
"FD build metadata",
)

replace_once(
'''                    choices = np.asarray([
                        i for i in eligible_indices[slot]
                        if i not in used and salary + salaries[i] <= salary_max
                    ], dtype=int)
''',
'''                    base_choices = eligible_indices[slot]
                    if used:
                        unused_mask = ~np.isin(base_choices, np.fromiter(used, dtype=int, count=len(used)))
                    else:
                        unused_mask = np.ones(len(base_choices), dtype=bool)
                    choices = base_choices[unused_mask & (salary + salaries[base_choices] <= salary_max)]
''',
"FD Full Roster slot choices",
)

replace_once(
'''                            choices = np.asarray([
                                i for i in choices
                                if (
                                    salary + int(salaries[i]) + max_remaining_salary >= salary_min
                                    and salary + int(salaries[i]) + min_remaining_salary <= salary_max
                                )
                            ], dtype=int)
''',
'''                            projected_salary = salary + salaries[choices]
                            choices = choices[
                                (projected_salary + max_remaining_salary >= salary_min)
                                & (projected_salary + min_remaining_salary <= salary_max)
                            ]
''',
"FD Full Roster salary feasibility",
)

replace_once(
'''                        choices = np.asarray([
                            i for i in choices
                            if salary_min <= salary + int(salaries[i]) <= salary_max
                        ], dtype=int)
''',
'''                        projected_salary = salary + salaries[choices]
                        choices = choices[(projected_salary >= salary_min) & (projected_salary <= salary_max)]
''',
"FD Full Roster final salary feasibility",
)

replace_once(
'''                        qb_name = str(chosen.get("QB", ""))
                        qb_matches = np.flatnonzero(names == qb_name)
                        if len(qb_matches):
                            qb_i = int(qb_matches[0])
                            qb_team = str(pool.iloc[qb_i].get("Team", "")).strip().upper()
                            qb_opp = str(pool.iloc[qb_i].get("Opponent", "")).strip().upper()
''',
'''                        qb_name = str(chosen.get("QB", ""))
                        qb_i = fd_build_name_to_index.get(qb_name)
                        if qb_i is not None:
                            qb_team = str(fd_build_teams[qb_i])
                            qb_opp = str(fd_build_opponents[qb_i])
''',
"FD Full Roster QB metadata",
)

replace_once(
'''                                hits = np.flatnonzero(names == str(picked_name))
                                if not len(hits):
                                    continue
                                row = pool.iloc[int(hits[0])]
                                pos = str(row.get("Position", "")).upper().split("/")[0]
                                if pos not in {"RB", "WR", "TE"}:
                                    continue
                                team = str(row.get("Team", "")).strip().upper()
''',
'''                                picked_i = fd_build_name_to_index.get(str(picked_name))
                                if picked_i is None:
                                    continue
                                pos = str(fd_build_positions[picked_i])
                                if pos not in {"RB", "WR", "TE"}:
                                    continue
                                team = str(fd_build_teams[picked_i])
''',
"FD Full Roster chosen stack metadata",
)

replace_once(
'''                                forced = [i for i in choices if str(pool.iloc[i].get("Team", "")).strip().upper() == qb_team]
                            elif need_bring and bring_now < 1 and skill_slots_left <= 1:
                                forced = [i for i in choices if str(pool.iloc[i].get("Team", "")).strip().upper() == qb_opp]
                            if forced:
                                mask = np.isin(choices, np.asarray(forced, dtype=int))
''',
'''                                forced = choices[fd_build_teams[choices] == qb_team]
                            elif need_bring and bring_now < 1 and skill_slots_left <= 1:
                                forced = choices[fd_build_teams[choices] == qb_opp]
                            if len(forced):
                                mask = np.isin(choices, np.asarray(forced, dtype=int))
''',
"FD Full Roster forced stack choices",
)

APP.write_text(text, encoding="utf-8")
print("Installed FanDuel Full Roster vectorized builder hot-loop optimizations")
