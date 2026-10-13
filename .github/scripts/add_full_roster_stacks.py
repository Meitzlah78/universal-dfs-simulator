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
'''def ownership_adjusted_player_scores(pool, names, base_scores, player_sim, projection_fallback=None):
''',
'''def full_roster_stack_matches(chosen, pool, selected_stacks):
    """Return True when a full-roster lineup matches at least one selected QB stack rule."""
    selected_stacks = list(selected_stacks or [])
    if not selected_stacks or "No stack rule" in selected_stacks:
        return True
    if not isinstance(pool, pd.DataFrame) or pool.empty or not isinstance(chosen, dict):
        return False

    lookup = pool.drop_duplicates("Name", keep="first").set_index("Name")
    qb_name = str(chosen.get("QB", "")).strip()
    if not qb_name or qb_name not in lookup.index:
        return False
    qb_row = lookup.loc[qb_name]
    qb_team = str(qb_row.get("Team", "")).strip().upper()
    qb_opp = str(qb_row.get("Opponent", "")).strip().upper()
    if not qb_team:
        return False

    same_team = 0
    bring_back = 0
    for slot, player in chosen.items():
        if slot == "QB":
            continue
        name = str(player).strip()
        if not name or name not in lookup.index:
            continue
        row = lookup.loc[name]
        pos = str(row.get("Position", "")).upper().replace(" ", "")
        primary = pos.split("/")[0]
        # Count offensive skill players only. DST/D do not satisfy stacks.
        if primary not in {"RB", "WR", "TE"}:
            continue
        team = str(row.get("Team", "")).strip().upper()
        if team == qb_team:
            same_team += 1
        if qb_opp and team == qb_opp:
            bring_back += 1

    rules = {
        "QB + 1 teammate": same_team >= 1,
        "QB + 2 teammates": same_team >= 2,
        "QB + 3 teammates": same_team >= 3,
        "QB + 1 teammate + bring-back": same_team >= 1 and bring_back >= 1,
        "QB + 2 teammates + bring-back": same_team >= 2 and bring_back >= 1,
        "QB + 3 teammates + bring-back": same_team >= 3 and bring_back >= 1,
    }
    return any(bool(rules.get(rule, False)) for rule in selected_stacks)


def opponent_field_selection_weights(pool, fallback_scores):
    """Use ownership as the primary opponent-construction signal for full-roster contests."""
    fallback = np.asarray(fallback_scores, dtype=float)
    lookup = {str(c).strip().casefold(): c for c in pool.columns}
    own_col = next((lookup[k] for k in (
        "field own %", "ownership %", "projected ownership", "ownership", "own%", "own"
    ) if k in lookup), None)
    if own_col is not None:
        ownership = pd.to_numeric(pool[own_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        ownership = np.clip(ownership, 0.0, None)
        if ownership.sum() > 0:
            return np.clip(ownership, 0.01, None)

    # Before field ownership exists, use a soft projection-rank proxy rather than
    # forcing the user's stack rules onto opponents.
    if not len(fallback):
        return fallback
    ranks = pd.Series(fallback).rank(pct=True).to_numpy(dtype=float)
    return np.clip(0.10 + ranks ** 2, 0.01, None)


def ownership_adjusted_player_scores(pool, names, base_scores, player_sim, projection_fallback=None):
''',
"stack and opponent ownership helpers",
)

# FanDuel Full Roster stack selector.
replace_once(
'''        else:
            st.caption(
                "FanDuel NFL Full Roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), D. "
                "Salary cap: $60,000."
            )
            fd_slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "D"]

        if fd_build_clicked:
''',
'''        else:
            st.caption(
                "FanDuel NFL Full Roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), D. "
                "Salary cap: $60,000."
            )
            fd_slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "D"]

        fd_stack_rules = []
        if lineup_mode == "Full Roster":
            fd_stack_rules = st.multiselect(
                "Stacks to use in MY lineups",
                [
                    "No stack rule",
                    "QB + 1 teammate",
                    "QB + 2 teammates",
                    "QB + 3 teammates",
                    "QB + 1 teammate + bring-back",
                    "QB + 2 teammates + bring-back",
                    "QB + 3 teammates + bring-back",
                ],
                default=["QB + 2 teammates + bring-back"],
                key="fd_full_roster_stack_rules",
                help="Choose one or more allowed stack types. A lineup is accepted if it matches any selected rule. Opponent lineups ignore these rules."
            )
            st.caption("These stack rules affect only your FanDuel builds. Simulated opponents remain ownership-driven.")

        if fd_build_clicked:
''',
"FD stack selector",
)

replace_once(
'''                if len(chosen) != len(slots) or salary < salary_min or salary > salary_max:
                    continue
                lineup_key = tuple(chosen[slot] for slot in slots)
''',
'''                if len(chosen) != len(slots) or salary < salary_min or salary > salary_max:
                    continue
                if lineup_mode == "Full Roster" and not full_roster_stack_matches(chosen, pool, fd_stack_rules):
                    continue
                lineup_key = tuple(chosen[slot] for slot in slots)
''',
"FD enforce stacks",
)

# FanDuel opponent weights: ownership first, independent of user stack choices.
replace_once(
'''            fd_pool["Projection"] = pd.to_numeric(fd_pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01)
            fd_weights = fd_pool["Projection"].to_numpy(dtype=float)
            fd_weights = fd_weights / fd_weights.sum() if fd_weights.sum() else np.full(len(fd_pool), 1 / max(len(fd_pool), 1))
''',
'''            fd_pool["Projection"] = pd.to_numeric(fd_pool["Projection"], errors="coerce").fillna(0.01).clip(lower=0.01)
            fd_weights = opponent_field_selection_weights(
                fd_pool, fd_pool["Projection"].to_numpy(dtype=float)
            )
            fd_weights = fd_weights / fd_weights.sum() if fd_weights.sum() else np.full(len(fd_pool), 1 / max(len(fd_pool), 1))
''',
"FD ownership weights base",
)

# Use the precomputed ownership-driven weights in FD Full Roster opponent picks.
replace_once(
'''                                weights = choices["Projection"].to_numpy(dtype=float)
                                weights = weights / weights.sum()
                                picked = choices.iloc[int(rng.choice(len(choices), p=weights))]
''',
'''                                choice_indices = choices.index.to_numpy(dtype=int)
                                weights = fd_weights[choice_indices].astype(float)
                                weights = weights / weights.sum() if weights.sum() else np.full(len(choices), 1.0 / len(choices))
                                picked = choices.iloc[int(rng.choice(len(choices), p=weights))]
''',
"FD full roster ownership picks",
)

# DraftKings Classic stack selector immediately before its build.
replace_once(
'''            locked_name_set = set(classic_locked_players)
            locked_indices = {
''',
'''            dk_classic_stack_rules = st.multiselect(
                "Stacks to use in MY lineups",
                [
                    "No stack rule",
                    "QB + 1 teammate",
                    "QB + 2 teammates",
                    "QB + 3 teammates",
                    "QB + 1 teammate + bring-back",
                    "QB + 2 teammates + bring-back",
                    "QB + 3 teammates + bring-back",
                ],
                default=["QB + 2 teammates + bring-back"],
                key="dk_classic_stack_rules",
                help="Choose one or more allowed stack types. A lineup is accepted if it matches any selected rule. Opponent lineups ignore these rules."
            )
            st.caption("These stack rules affect only your DraftKings Classic builds. Simulated opponents remain ownership-driven.")

            locked_name_set = set(classic_locked_players)
            locked_indices = {
''',
"DK Classic stack selector",
)

replace_once(
'''                if not locked_name_set.issubset(set(chosen.values())):
                    continue
                key = tuple(chosen[slot] for slot, _ in roster_slots)
''',
'''                if not locked_name_set.issubset(set(chosen.values())):
                    continue
                if not full_roster_stack_matches(chosen, classic_pool, dk_classic_stack_rules):
                    continue
                key = tuple(chosen[slot] for slot, _ in roster_slots)
''',
"DK Classic enforce stacks",
)

# DraftKings Classic opponents: ownership is primary; stack rules are not applied.
replace_once(
'''                    pool["MeanPoints"] = pool["Name"].map(mean_scores).fillna(pool["Projection"])
                    pool["Weight"] = pool["MeanPoints"].clip(lower=0.01)
''',
'''                    pool["MeanPoints"] = pool["Name"].map(mean_scores).fillna(pool["Projection"])
                    pool["Weight"] = opponent_field_selection_weights(
                        pool, pool["MeanPoints"].to_numpy(dtype=float)
                    )
''',
"DK Classic opponent ownership weights",
)

APP.write_text(text, encoding="utf-8")
print("Patched full-roster stack controls and ownership-driven opponents")
