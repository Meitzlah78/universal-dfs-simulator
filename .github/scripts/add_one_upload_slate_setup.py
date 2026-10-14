from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# Speed up full-roster builds by steering player selection toward the selected
# QB stack while the lineup is being built. The final stack validation remains
# in place, so lineup rules do not change; far fewer attempts are rejected.
fd_old = '''                else:
                    for slot, _ in roster:
                        choices = np.asarray([
                            i for i in eligible_indices[slot]
                            if i not in used and salary + salaries[i] <= salary_max
                        ], dtype=int)
                        if not len(choices):
                            break
                        weights = lineup_scores[choices].copy()
'''
fd_new = '''                else:
                    for slot, _ in roster:
                        choices = np.asarray([
                            i for i in eligible_indices[slot]
                            if i not in used and salary + salaries[i] <= salary_max
                        ], dtype=int)
                        if not len(choices):
                            break
                        weights = lineup_scores[choices].copy()
                        # Build the requested QB stack during generation instead of
                        # relying only on post-build rejection.
                        if lineup_mode == "Full Roster" and slot != "QB" and "QB" in chosen and fd_stack_rules and "No stack rule" not in fd_stack_rules:
                            qb_name = str(chosen.get("QB", ""))
                            qb_matches = np.flatnonzero(names == qb_name)
                            if len(qb_matches):
                                qb_i = int(qb_matches[0])
                                qb_team = str(pool.iloc[qb_i].get("Team", "")).strip().upper()
                                qb_opp = str(pool.iloc[qb_i].get("Opponent", "")).strip().upper()
                                need_same = max([3 if "QB + 3 teammate" in r else 2 if "QB + 2 teammate" in r else 1 for r in fd_stack_rules] or [1])
                                need_bring = any("bring-back" in r for r in fd_stack_rules)
                                same_now = 0
                                bring_now = 0
                                for picked_name in chosen.values():
                                    if picked_name == qb_name:
                                        continue
                                    hits = np.flatnonzero(names == str(picked_name))
                                    if not len(hits):
                                        continue
                                    row = pool.iloc[int(hits[0])]
                                    pos = str(row.get("Position", "")).upper().split("/")[0]
                                    if pos not in {"RB", "WR", "TE"}:
                                        continue
                                    team = str(row.get("Team", "")).strip().upper()
                                    same_now += int(team == qb_team)
                                    bring_now += int(bool(qb_opp) and team == qb_opp)
                                skill_slots_left = sum(1 for s, e in roster[roster.index((slot, _)):] if e & {"RB", "WR", "TE"})
                                forced = []
                                if same_now < need_same and skill_slots_left <= (need_same - same_now) + (1 if need_bring and bring_now < 1 else 0):
                                    forced = [i for i in choices if str(pool.iloc[i].get("Team", "")).strip().upper() == qb_team]
                                elif need_bring and bring_now < 1 and skill_slots_left <= 1:
                                    forced = [i for i in choices if str(pool.iloc[i].get("Team", "")).strip().upper() == qb_opp]
                                if forced:
                                    mask = np.isin(choices, np.asarray(forced, dtype=int))
                                    weights = np.where(mask, weights * 25.0, weights)
'''
if fd_old in text:
    text = text.replace(fd_old, fd_new, 1)

classic_old = '''                for slot, _eligible in roster_slots:
                    choices = np.asarray([
                        i for i in eligible_indices[slot]
                        if i not in used and salary + classic_salaries[i] <= MAX_LINEUP_SALARY
                    ], dtype=int)
                    if not len(choices):
                        break
                    weights = classic_weights[choices].copy()
'''
classic_new = '''                for slot, _eligible in roster_slots:
                    choices = np.asarray([
                        i for i in eligible_indices[slot]
                        if i not in used and salary + classic_salaries[i] <= MAX_LINEUP_SALARY
                    ], dtype=int)
                    if not len(choices):
                        break
                    weights = classic_weights[choices].copy()
                    # Build the requested QB stack during generation instead of
                    # relying only on post-build rejection.
                    if slot != "QB" and "QB" in chosen and dk_classic_stack_rules and "No stack rule" not in dk_classic_stack_rules:
                        qb_name = str(chosen.get("QB", ""))
                        qb_matches = np.flatnonzero(classic_names == qb_name)
                        if len(qb_matches):
                            qb_i = int(qb_matches[0])
                            qb_team = str(classic_pool.iloc[qb_i].get("Team", "")).strip().upper()
                            qb_opp = str(classic_pool.iloc[qb_i].get("Opponent", "")).strip().upper()
                            need_same = max([3 if "QB + 3 teammate" in r else 2 if "QB + 2 teammate" in r else 1 for r in dk_classic_stack_rules] or [1])
                            need_bring = any("bring-back" in r for r in dk_classic_stack_rules)
                            same_now = 0
                            bring_now = 0
                            for picked_name in chosen.values():
                                if picked_name == qb_name:
                                    continue
                                hits = np.flatnonzero(classic_names == str(picked_name))
                                if not len(hits):
                                    continue
                                row = classic_pool.iloc[int(hits[0])]
                                pos = str(row.get("Position", "")).upper().split("/")[0]
                                if pos not in {"RB", "WR", "TE"}:
                                    continue
                                team = str(row.get("Team", "")).strip().upper()
                                same_now += int(team == qb_team)
                                bring_now += int(bool(qb_opp) and team == qb_opp)
                            current_pos = next((j for j, (s, _) in enumerate(roster_slots) if s == slot), 0)
                            skill_slots_left = sum(1 for _, e in roster_slots[current_pos:] if e & {"RB", "WR", "TE"})
                            forced = []
                            if same_now < need_same and skill_slots_left <= (need_same - same_now) + (1 if need_bring and bring_now < 1 else 0):
                                forced = [i for i in choices if str(classic_pool.iloc[i].get("Team", "")).strip().upper() == qb_team]
                            elif need_bring and bring_now < 1 and skill_slots_left <= 1:
                                forced = [i for i in choices if str(classic_pool.iloc[i].get("Team", "")).strip().upper() == qb_opp]
                            if forced:
                                mask = np.isin(choices, np.asarray(forced, dtype=int))
                                weights = np.where(mask, weights * 25.0, weights)
'''
if classic_old in text:
    text = text.replace(classic_old, classic_new, 1)

path.write_text(text, encoding="utf-8")
print("Applied faster stack-aware DK Classic and FanDuel Full Roster builders")
