from pathlib import Path

p = Path('dfs_app.py')
s = p.read_text()

s = s.replace(
    'batch_valid = (batch_salary >= int(min_salary)) & (batch_salary <= int(max_salary)) & (batch_salary <= int(SALARY_CAP))',
    'batch_valid = (batch_salary >= int(MIN_LINEUP_SALARY)) & (batch_salary <= int(min(SALARY_CAP, MAX_LINEUP_SALARY)))',
    1,
)

old = '''                sampled_indices = sampled_indices[batch_valid]\n\n                for sampled_idx in sampled_indices:\n                    if len(captain_candidates) >= per_captain_candidate_limit:\n                        break\n                    sampled = flex_names[sampled_idx]\n                    flex_players = tuple(str(p) for p in sampled)\n                    flex_key = tuple(sorted(flex_players))\n                    if flex_key in seen_flex_groups:\n                        continue\n                    seen_flex_groups.add(flex_key)\n\n                    lineup_players = [\n                        captain\n                    ] + list(flex_players)\n\n                    # LOCK CHECK\n                    if not all(\n                        p in lineup_players\n                        for p in locked_players\n                    ):\n                        continue\n\n                    # SALARY CHECK\n                    total_salary = (\n                        captain_salary_map[captain]\n                        + sum(\n                            salary_map[p]\n                            for p in flex_players\n                        )\n                    )\n\n                    if total_salary < MIN_LINEUP_SALARY or total_salary > min(SALARY_CAP, MAX_LINEUP_SALARY):\n                        continue\n\n                    # DraftKings Showdown requires players\n                    # from both teams\n                    lineup_teams = set(\n                        players_df.loc[\n                            players_df["Name"].isin(lineup_players),\n                            "Team"\n                        ]\n                    )\n\n                    if len(lineup_teams) < 2:\n                        continue\n'''
new = '''                for sampled_row, sampled_idx in enumerate(sampled_indices):\n                    if len(captain_candidates) >= per_captain_candidate_limit:\n                        break\n                    sampled = flex_names[sampled_idx]\n                    flex_players = tuple(str(p) for p in sampled)\n                    flex_key = tuple(sorted(flex_players))\n                    if flex_key in seen_flex_groups:\n                        continue\n                    # Preserve the original search semantics: every first-seen FLEX group\n                    # consumes its seen slot even when it later fails a lineup rule.\n                    seen_flex_groups.add(flex_key)\n                    if not bool(batch_valid[sampled_row]):\n                        continue\n\n                    total_salary = int(batch_salary[sampled_row])\n'''
if s.count(old) != 1:
    raise SystemExit('SAFE_ABORT vector candidate body anchor')
s = s.replace(old, new, 1)
p.write_text(s)
