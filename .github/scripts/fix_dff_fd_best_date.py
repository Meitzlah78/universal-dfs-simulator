from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''            dff_debug = []
            for slate_date in recent_dates:
'''
new='''            dff_debug = []
            best_values = {}
            best_overlap = 0
            best_date = None
            for slate_date in recent_dates:
'''
if old not in s: raise SystemExit('start block not found')
s=s.replace(old,new,1)
old2='''                    dff_debug.append(f"{slate_date}: rows={len(values)}, overlap={len(overlap)}, name_col={name_col!r}, proj_col={proj_col!r}, sample={_sample_keys!r}")
                    if len(overlap) >= min(2, len(target_keys)):
                        return values
            st.warning("DFF FanDuel diagnostic — " + ("; ".join(dff_debug) if dff_debug else f"dates={recent_dates!r}; no projection table parsed"))
'''
new2='''                    dff_debug.append(f"{slate_date}: rows={len(values)}, overlap={len(overlap)}, name_col={name_col!r}, proj_col={proj_col!r}, sample={_sample_keys!r}")
                    if len(overlap) > best_overlap:
                        best_values = values
                        best_overlap = len(overlap)
                        best_date = slate_date
            if best_overlap >= min(2, len(target_keys)):
                return best_values
            st.warning("DFF FanDuel diagnostic — " + ("; ".join(dff_debug) if dff_debug else f"dates={recent_dates!r}; no projection table parsed"))
'''
if old2 not in s: raise SystemExit('return block not found')
s=s.replace(old2,new2,1)
p.write_text(s)
print('DFF FD now selects date with maximum salary-name overlap')
