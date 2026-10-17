from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
start=s.index('                    # DFF uses a 3-level header. Match the semantic second')
end=s.index('                    for name, projection in zip(table[name_col], table[proj_col]):', start)
new='''                    # FanDuel DFF rendered layout: player Name is the 7th displayed
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
'''
s=s[:start]+new+s[end:]
p.write_text(s)
print('DFF FanDuel name column set to displayed column 7')
