from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''                    dff_debug.append(f"{slate_date}: rows={len(values)}, overlap={len(overlap)}")'''
new='''                    _sample_keys = list(values.keys())[:5]\n                    dff_debug.append(f"{slate_date}: rows={len(values)}, overlap={len(overlap)}, name_col={name_col!r}, proj_col={proj_col!r}, sample={_sample_keys!r}")'''
if old not in s:
    raise SystemExit('diagnostic insertion point not found')
s=s.replace(old,new,1)
p.write_text(s)
print('Installed DFF sample diagnostic')