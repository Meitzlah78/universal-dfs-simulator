from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''                    name_col = proj_col = None
                    for col in table.columns:
                        levels = [re.sub(r"[^a-z0-9]+", " ", str(x).casefold()).strip() for x in col]
                        if "name" in levels:
                            name_col = col
                        if "fd fp projected" in levels:
                            proj_col = col
                    if name_col is None or proj_col is None:
                        continue
'''
new='''                    # DFF uses a 3-level header. Match the semantic second
                    # header level exactly so later columns cannot overwrite NAME.
                    name_col = proj_col = None
                    for col in table.columns:
                        levels = [re.sub(r"[^a-z0-9]+", " ", str(x).casefold()).strip() for x in col]
                        if len(levels) > 1 and levels[1] == "name" and name_col is None:
                            name_col = col
                        if len(levels) > 1 and levels[1] == "fd fp projected" and proj_col is None:
                            proj_col = col
                    # Current DFF table layout is NAME at column 1 and FD projected
                    # points at column 6. Use that only as a validated fallback.
                    if (name_col is None or proj_col is None) and table.shape[1] > 6:
                        name_col = table.columns[1]
                        proj_col = table.columns[6]
                    if name_col is None or proj_col is None:
                        continue
'''
if old not in s:
    raise SystemExit('DFF column-selection block not found')
s=s.replace(old,new,1)
p.write_text(s)
print('Fixed DFF FanDuel column selection')
