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


# Cache Full Roster metadata once before the bounded build. This keeps pandas
# filtering/name lookups out of the nine-slot hot loop while preserving all
# existing salary, lock, stack, exposure, scoring, and contest rules.
replace_once(
'''            pool = fd_pool.reset_index(drop=True).copy()
            names = pool["Name"].astype(str).to_numpy(dtype=object)
            salaries = pd.to_numeric(pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
''',
'''            pool = fd_pool.reset_index(drop=True).copy()
            names = pool["Name"].astype(str).to_numpy(dtype=object)
            salaries = pd.to_numeric(pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
            # Full Roster fast-build metadata. Single Game can share the cheap arrays,
            # but the slot eligibility below remains format-specific.
            fd_build_teams = pool.get("Team", pd.Series("", index=pool.index)).fillna("").astype(str).str.strip().str.upper().to_numpy(dtype=object)
            fd_build_opponents = pool.get("Opponent", pd.Series("", index=pool.index)).fillna("").astype(str).str.strip().str.upper().to_numpy(dtype=object)
            fd_build_positions = pool.get("Position", pd.Series("", index=pool.index)).fillna("").astype(str).str.upper().str.replace(" ", "", regex=False).str.split("/").str[0].to_numpy(dtype=object)
            fd_build_name_to_index = {str(name): i for i, name in enumerate(names)}
''',
"FD build metadata",
)

# Replace repeated DataFrame slot filtering in the user's Full Roster builder
# with precomputed integer index arrays. The roster definitions themselves are
# unchanged: QB, 2 RB, 3 WR, TE, FLEX, D.
replace_once(
'''            slot_eligibility = {}
            for slot in fd_slots:
                slot_eligibility[slot] = pool.index[
                    pool.apply(lambda row: fd_slot_eligible(row, slot), axis=1)
                ].to_numpy(dtype=int)
''',
'''            slot_eligibility = {}
            if lineup_mode == "Full Roster":
                fd_position_masks = {
                    "QB": fd_build_positions == "QB",
                    "RB": fd_build_positions == "RB",
                    "WR": fd_build_positions == "WR",
                    "TE": fd_build_positions == "TE",
                    "D": np.isin(fd_build_positions, np.asarray(["D", "DEF", "DST"], dtype=object)),
                }
                for slot in fd_slots:
                    if slot == "QB":
                        mask = fd_position_masks["QB"]
                    elif slot.startswith("RB"):
                        mask = fd_position_masks["RB"]
                    elif slot.startswith("WR"):
                        mask = fd_position_masks["WR"]
                    elif slot == "TE":
                        mask = fd_position_masks["TE"]
                    elif slot == "FLEX":
                        mask = fd_position_masks["RB"] | fd_position_masks["WR"] | fd_position_masks["TE"]
                    elif slot == "D":
                        mask = fd_position_masks["D"]
                    else:
                        mask = np.zeros(len(pool), dtype=bool)
                    slot_eligibility[slot] = np.flatnonzero(mask)
            else:
                for slot in fd_slots:
                    slot_eligibility[slot] = pool.index[
                        pool.apply(lambda row: fd_slot_eligible(row, slot), axis=1)
                    ].to_numpy(dtype=int)
''',
"FD slot eligibility",
)

# Vectorize used-player and salary filtering inside each roster slot.
replace_once(
'''                    choices = np.asarray([
                        i for i in slot_eligibility[slot]
                        if i not in used and salary + salaries[i] <= salary_max
                    ], dtype=int)
''',
'''                    base_choices = slot_eligibility[slot]
                    if used:
                        unused_mask = ~np.isin(base_choices, np.fromiter(used, dtype=int, count=len(used)))
                    else:
                        unused_mask = np.ones(len(base_choices), dtype=bool)
                    salary_mask = salary + salaries[base_choices] <= salary_max
                    choices = base_choices[unused_mask & salary_mask]
''',
"FD slot choices",
)

APP.write_text(text, encoding="utf-8")
print("Installed FanDuel Full Roster vectorized builder hot-loop optimizations")
