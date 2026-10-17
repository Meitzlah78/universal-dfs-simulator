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
'''        names = pool["Name"].astype(str).to_numpy(dtype=object)
        salaries = pd.to_numeric(pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
        projections = pd.to_numeric(pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01).to_numpy(dtype=float)
''',
'''        names = pool["Name"].astype(str).to_numpy(dtype=object)
        salaries = pd.to_numeric(pool["Salary"], errors="coerce").fillna(0).to_numpy(dtype=np.int64)
        fd_all_player_indices = np.arange(len(names), dtype=int)
        fd_build_name_to_index = {str(name): i for i, name in enumerate(names)}
        fd_build_teams = pool.get("Team", pd.Series("", index=pool.index)).fillna("").astype(str).str.strip().str.upper().to_numpy(dtype=object)
        fd_build_opponents = pool.get("Opponent", pd.Series("", index=pool.index)).fillna("").astype(str).str.strip().str.upper().to_numpy(dtype=object)
        fd_build_positions = pool.get("Position", pd.Series("", index=pool.index)).fillna("").astype(str).str.upper().str.replace(" ", "", regex=False).str.split("/").str[0].to_numpy(dtype=object)
        fd_stack_lookup = pool.drop_duplicates("Name", keep="first").set_index("Name") if lineup_mode == "Full Roster" else None
        projections = pd.to_numeric(pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01).to_numpy(dtype=float)
''',
"shared FanDuel build metadata",
)

APP.write_text(text, encoding="utf-8")
print("Installed shared FanDuel builder metadata precomputation")
