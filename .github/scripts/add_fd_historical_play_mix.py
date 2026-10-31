from pathlib import Path
p=Path('dfs_app.py'); s=p.read_text()
old='''            plays_by_sim = np.clip(np.rint(rng.normal(64.0, 6.5, n) * game_pace), 48, 82).astype(int)
            side_sign = 1.0 if side_i == 0 else -1.0
'''
new='''            # Team play volume and pass/run mix come from the historical roles above.
            # QB attempts represent historical dropback/pass volume; RB + QB carries
            # represent rushing volume. Current projections remain a secondary signal
            # through player allocation, not a post-simulation fantasy-point correction.
            _qb_role = _fd_hist_roles.get(qb_name, {}) if qb_name else {}
            _hist_pass = float(_qb_role.get("pass_attempts", 0.0))
            _hist_rb_rush = float(sum(max(_fd_hist_roles.get(x, {}).get("carries", 0.0), 0.0) for x in rb_names))
            _hist_qb_rush = float(_qb_role.get("carries", 0.0))
            _hist_rush = _hist_rb_rush + _hist_qb_rush
            _hist_plays = _hist_pass + _hist_rush
            _base_plays = float(np.clip(_hist_plays, 52.0, 76.0)) if _hist_plays >= 40.0 else 64.0
            _base_pass_rate = float(np.clip(_hist_pass / max(_hist_plays, 1.0), 0.44, 0.70)) if _hist_plays >= 40.0 else 0.58
            plays_by_sim = np.clip(np.rint(rng.normal(_base_plays, 5.5, n) * game_pace), 46, 84).astype(int)
            side_sign = 1.0 if side_i == 0 else -1.0
'''
if old not in s:
    if '_base_pass_rate' in s: print('Historical play mix already applied'); raise SystemExit(0)
    raise SystemExit('play volume anchor missing')
s=s.replace(old,new,1)
old2='''                pass_rate = float(np.clip(0.58 - 0.025 * edge, 0.43, 0.72))
'''
new2='''                pass_rate = float(np.clip(_base_pass_rate - 0.025 * edge, 0.40, 0.74))
'''
if old2 not in s: raise SystemExit('pass-rate anchor missing')
s=s.replace(old2,new2,1)
p.write_text(s)
print('Applied historical team play volume and pass/run mix to FanDuel PBP')
