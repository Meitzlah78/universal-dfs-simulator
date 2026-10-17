from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''                    for name, projection in zip(table[name_col], table[proj_col]):
                        key = normalize_projection_player_name(name)
                        val = pd.to_numeric(projection, errors="coerce")
'''
new='''                    # DFF's rendered table has POS values under the column whose
                    # second header level says NAME. The actual player names are
                    # in the first column (header level 0 == PLAYER).
                    player_col = None
                    for col in table.columns:
                        levels = [re.sub(r"[^a-z0-9]+", " ", str(x).casefold()).strip() for x in col]
                        if levels and levels[0] == "player":
                            player_col = col
                            break
                    if player_col is None:
                        player_col = table.columns[0]
                    name_col = player_col
                    for name, projection in zip(table[name_col], table[proj_col]):
                        key = normalize_projection_player_name(name)
                        val = pd.to_numeric(projection, errors="coerce")
'''
if old not in s:
    raise SystemExit('DFF value loop not found')
s=s.replace(old,new,1)
p.write_text(s)
print('Fixed DFF FanDuel player-name column')
