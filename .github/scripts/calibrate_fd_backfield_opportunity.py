from pathlib import Path
p=Path('dfs_app.py'); s=p.read_text()
# Keep the historical RB carry-share correction, but remove the RB/non-RB receiving
# buckets. Targets are allocated across the entire eligible receiving corps by each
# player's individual historical team target share blended with current projection.
start=s.find('''            # Backfield receiving opportunity is constrained by historical RB targets.''')
end=s.find('''            # Team play volume and pass/run mix come from the historical roles above.''', start)
if start >= 0 and end > start:
    replacement='''            # Allocate receiving opportunity by INDIVIDUAL historical team target share.
            # This preserves alpha WR/TE volume while still keeping RB receiving work tied
            # to the same finite team target pool. Projection is a secondary current-role
            # signal rather than a separate positional bucket.
            if len(rec_names):
                _rec_hist_raw = np.asarray([max(_fd_hist_roles.get(str(x), {}).get("targets", 0.0), 0.0) for x in rec_names], dtype=float)
                _rec_proj_raw = np.clip(recs["Projection"].to_numpy(dtype=float), 0.05, None)
                _rec_proj_share = _rec_proj_raw / max(float(_rec_proj_raw.sum()), 0.01)
                if _rec_hist_raw.sum() > 0:
                    _rec_hist_share = _rec_hist_raw / _rec_hist_raw.sum()
                    # History carries most of the role signal; projection lets current
                    # depth-chart changes move opportunity without erasing alpha roles.
                    rec_w = 0.78 * _rec_hist_share + 0.22 * _rec_proj_share
                else:
                    rec_w = _rec_proj_share
                rec_w = rec_w / rec_w.sum()

'''
    s=s[:start]+replacement+s[end:]
elif 'INDIVIDUAL historical team target share' not in s:
    raise SystemExit('receiving bucket block missing')
# Ensure carry correction remains installed even if this script is rerun on a clean app.
old='''            if len(rbs):
                _rb_proj = np.clip(rbs["Projection"].to_numpy(dtype=float), 0.05, None)
                _rb_hist = np.asarray([max(_fd_hist_roles.get(str(x), {}).get("carries", 0.0), 0.0) for x in rb_names], dtype=float)
                if _rb_hist.sum() > 0:
                    _rb_hist = _rb_hist / _rb_hist.sum()
                    _rb_proj = _rb_proj / _rb_proj.sum()
                    rb_w = 0.75 * _rb_hist + 0.25 * _rb_proj
                else:
                    rb_w = _rb_proj / _rb_proj.sum()
            else: rb_w = np.array([])
'''
new='''            if len(rbs):
                _rb_proj = np.clip(rbs["Projection"].to_numpy(dtype=float), 0.05, None)
                _rb_hist_raw = np.asarray([max(_fd_hist_roles.get(str(x), {}).get("carries", 0.0), 0.0) for x in rb_names], dtype=float)
                _rb_hist_carries_total = float(_rb_hist_raw.sum())
                if _rb_hist_carries_total > 0:
                    _rb_hist = _rb_hist_raw / _rb_hist_carries_total
                    _rb_proj = _rb_proj / _rb_proj.sum()
                    rb_w = 0.82 * _rb_hist + 0.18 * _rb_proj
                else:
                    rb_w = _rb_proj / _rb_proj.sum()
            else:
                rb_w = np.array([])
                _rb_hist_carries_total = 0.0
'''
if old in s: s=s.replace(old,new,1)
s=s.replace('''                        _rb_carries_hist = float(sum(max(_fd_hist_roles.get(x, {}).get("carries", 0.0), 0.0) for x in rb_names))
''','''                        _rb_carries_hist = _rb_hist_carries_total
''',1)
p.write_text(s)
print('Kept RB carry calibration and restored individual historical team target shares')
