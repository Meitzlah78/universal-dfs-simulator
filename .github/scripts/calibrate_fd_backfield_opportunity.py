from pathlib import Path
p=Path('dfs_app.py'); s=p.read_text()
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

            # Backfield receiving opportunity is constrained by historical RB targets.
            # This prevents the RB room from inheriting an oversized share merely because
            # RB fantasy projections are strong. WR/TE and RB target shares are normalized
            # separately, then blended with a small projection signal inside each group.
            _rb_target_total = float(sum(max(_fd_hist_roles.get(x, {}).get("targets", 0.0), 0.0) for x in rb_names))
            _nonrb_rec_names = [x for x in rec_names if x not in set(rb_names)]
            _nonrb_target_total = float(sum(max(_fd_hist_roles.get(x, {}).get("targets", 0.0), 0.0) for x in _nonrb_rec_names))
            _all_hist_targets = _rb_target_total + _nonrb_target_total
            _rb_target_share = float(np.clip(_rb_target_total / max(_all_hist_targets, 1.0), 0.08, 0.34)) if _all_hist_targets > 0 else 0.18
            if len(rec_names):
                _rec_hist_raw = np.asarray([max(_fd_hist_roles.get(str(x), {}).get("targets", 0.0), 0.0) for x in rec_names], dtype=float)
                _rec_proj_raw = np.clip(recs["Projection"].to_numpy(dtype=float), 0.05, None)
                _rb_mask = np.asarray([x in set(rb_names) for x in rec_names], dtype=bool)
                _new_rec_w = np.zeros(len(rec_names), dtype=float)
                for _mask, _group_share in ((_rb_mask, _rb_target_share), (~_rb_mask, 1.0 - _rb_target_share)):
                    if not np.any(_mask):
                        continue
                    _h = _rec_hist_raw[_mask]
                    _pr = _rec_proj_raw[_mask]
                    _h = (_h / _h.sum()) if _h.sum() > 0 else np.full(len(_h), 1.0 / len(_h))
                    _pr = _pr / _pr.sum()
                    _new_rec_w[_mask] = _group_share * (0.82 * _h + 0.18 * _pr)
                if _new_rec_w.sum() > 0:
                    rec_w = _new_rec_w / _new_rec_w.sum()
'''
if old in s: s=s.replace(old,new,1)
elif '_rb_target_share' not in s: raise SystemExit('backfield weight anchor missing')
# Use the already-computed historical RB carry total in the QB-v-RB run split.
s=s.replace('''                        _rb_carries_hist = float(sum(max(_fd_hist_roles.get(x, {}).get("carries", 0.0), 0.0) for x in rb_names))
                        _qb_rush_share = float(np.clip(_qb_carries_hist / max(_qb_carries_hist + _rb_carries_hist, 1.0), 0.0, 0.35))
''','''                        _rb_carries_hist = _rb_hist_carries_total
                        _qb_rush_share = float(np.clip(_qb_carries_hist / max(_qb_carries_hist + _rb_carries_hist, 1.0), 0.0, 0.35))
''',1)
p.write_text(s)
print('Calibrated FanDuel RB carry and target opportunity to historical backfield shares')
