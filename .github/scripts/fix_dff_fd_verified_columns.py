from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''                    # DFF's MultiIndex labels are shifted relative to the rendered data.
                    # Runtime diagnostics show physical column 6 contains player names.
                    # The FD projected-points data is the next physical column (7), even
                    # though its semantic header is attached to column 6.
                    if table.shape[1] <= 7:
                        continue
                    name_col = table.columns[6]
                    proj_col = table.columns[7]
                    values = {}
                    for name, projection in zip(table.iloc[:, 6], table.iloc[:, 7]):
'''
new='''                    # Verified against the live DFF FanDuel table in Actions:
                    # parsed physical column 2 = player name, column 7 = FD projection.
                    # (The MultiIndex labels are shifted relative to the row values.)
                    if table.shape[1] <= 7:
                        continue
                    name_col = table.columns[2]
                    proj_col = table.columns[7]
                    values = {}
                    for name, projection in zip(table.iloc[:, 2], table.iloc[:, 7]):
'''
if old not in s:
    raise SystemExit('DFF physical parser block not found')
s=s.replace(old,new,1)
p.write_text(s)
print('DFF FD verified mapping: name index 2, projection index 7')
