from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''                        valid = np.all(np.diff(sorted_picks, axis=1) != 0, axis=1)
                        salaries = pool_salaries[picks].sum(axis=1)
                        valid &= (salaries >= MIN_LINEUP_SALARY) & (salaries <= MAX_LINEUP_SALARY) & (salaries <= 50000)
                        vp = picks[valid]
                        vs = salaries[valid]
                        if len(vp):
                            need = field_target - field_count
                            vp = vp[:need]
                            vs = vs[:need]
                            field_batches.append((vp, vs))
                            field_count += len(vp)
'''
new='''                        valid = np.all(np.diff(sorted_picks, axis=1) != 0, axis=1)
                        salaries = pool_salaries[picks].sum(axis=1)
                        valid &= (salaries >= MIN_LINEUP_SALARY) & (salaries <= MAX_LINEUP_SALARY) & (salaries <= 50000)
                        vp = picks[valid]
                        vs = salaries[valid]
                        if len(vp):
                            # A real DK Classic field is not a random collection of
                            # salary-valid rosters. Prefer stronger, higher-spend builds
                            # while retaining enough lower-salary/contrarian lineups to
                            # preserve field diversity and natural duplicates.
                            _vproj = pool_means[vp].sum(axis=1)
                            _proj_center = float(np.median(_vproj))
                            _proj_scale = max(float(np.std(_vproj)), 1.0)
                            _proj_z = np.clip((_vproj - _proj_center) / _proj_scale, -3.0, 3.0)
                            _salary_z = np.clip((vs.astype(float) - 48500.0) / 1200.0, -3.0, 1.25)
                            _human_weight = np.exp(0.85 * _proj_z + 0.55 * _salary_z)

                            # NFL Classic users strongly prefer QB stacks. Apply a soft
                            # construction preference rather than a hard stack rule.
                            _qb = vp[:, 0]
                            _qb_team = pool.iloc[_qb]["Team"].astype(str).to_numpy()
                            _skill_cols = vp[:, [1, 2, 3, 4, 5, 6, 7]]
                            _skill_teams = np.asarray(pool["Team"].astype(str).to_numpy()[_skill_cols])
                            _stack_count = (_skill_teams == _qb_team[:, None]).sum(axis=1)
                            _human_weight *= np.where(_stack_count >= 2, 2.0, np.where(_stack_count >= 1, 1.45, 0.45))

                            _human_weight = np.nan_to_num(_human_weight, nan=0.0, posinf=0.0, neginf=0.0)
                            if _human_weight.sum() > 0:
                                _human_weight /= _human_weight.sum()
                                _take = min(len(vp), max(field_target - field_count, 1))
                                _chosen = rng.choice(len(vp), size=_take, replace=True, p=_human_weight)
                                vp = vp[_chosen]
                                vs = vs[_chosen]
                            need = field_target - field_count
                            vp = vp[:need]
                            vs = vs[:need]
                            field_batches.append((vp, vs))
                            field_count += len(vp)
'''
if old not in s: raise SystemExit('target block not found')
s=s.replace(old,new,1)
p.write_text(s)
