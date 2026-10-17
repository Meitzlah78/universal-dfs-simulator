from pathlib import Path

p = Path('dfs_app.py')
s = p.read_text()
old = '''                    # FanDuel DFF rendered layout: player Name is the 7th displayed
                    # column. Use its physical position instead of misleading MultiIndex labels.
                    if table.shape[1] <= 6:
                        continue
                    name_col = table.columns[6]
                    proj_col = None
                    for col in table.columns:
                        levels = [re.sub(r"[^a-z0-9]+", " ", str(x).casefold()).strip() for x in col]
                        if len(levels) > 1 and levels[1] == "fd fp projected":
                            proj_col = col
                            break
                    if proj_col is None:
                        continue
                    values = {}
                    for name, projection in zip(table[name_col], table[proj_col]):
'''
new = '''                    # DFF's MultiIndex labels are shifted relative to the rendered data.
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
if old not in s:
    raise SystemExit('Current DFF FanDuel parser block not found')
s = s.replace(old, new, 1)
p.write_text(s)
print('Fixed DFF FanDuel physical name/projection columns')
