from pathlib import Path
p=Path('dfs_app.py'); s=p.read_text()
old='''                    "rec_tds": _avg("receiving_tds", "receiving_touchdowns", "rec_tds"),
                    "pass_attempts": _avg("attempts", "passing_attempts"),
                }
'''
new='''                    "rec_tds": _avg("receiving_tds", "receiving_touchdowns", "rec_tds"),
                    "pass_attempts": _avg("attempts", "passing_attempts"),
                    "completions": _avg("completions", "passing_completions"),
                    "pass_yards": _avg("passing_yards", "pass_yards"),
                    "pass_tds": _avg("passing_tds", "passing_touchdowns", "pass_tds"),
                    "interceptions": _avg("interceptions", "passing_interceptions"),
                }
'''
# replace only all-role dict occurrence (last suitable occurrence)
pos=s.find(old, s.find('# Historical opportunity/efficiency profiles'))
if pos>=0: s=s[:pos]+s[pos:].replace(old,new,1)
elif '"completions": _avg' not in s: raise SystemExit('historical role dict anchor missing')
old2='''                pass_rate = float(np.clip(_base_pass_rate - 0.025 * edge, 0.40, 0.74))
                for _ in range(int(plays_by_sim[sim_i])):
'''
new2='''                pass_rate = float(np.clip(_base_pass_rate - 0.025 * edge, 0.40, 0.74))
                _qb_hist = _fd_hist_roles.get(qb_name, {}) if qb_name else {}
                _qa = float(_qb_hist.get("pass_attempts", 0.0))
                _qc = float(_qb_hist.get("completions", 0.0))
                _qy = float(_qb_hist.get("pass_yards", 0.0))
                _qtd = float(_qb_hist.get("pass_tds", 0.0))
                _qint = float(_qb_hist.get("interceptions", 0.0))
                _qb_comp_rate = float(np.clip(_qc / max(_qa, 1.0), 0.52, 0.76)) if _qa > 0 else 0.64
                _qb_ypa = float(np.clip(_qy / max(_qa, 1.0), 5.4, 9.8)) if _qa > 0 else 7.1
                _qb_td_rate = float(np.clip(_qtd / max(_qa, 1.0), 0.020, 0.090)) if _qa > 0 else 0.045
                _qb_int_rate = float(np.clip(_qint / max(_qa, 1.0), 0.006, 0.050)) if _qa > 0 else 0.021
                for _ in range(int(plays_by_sim[sim_i])):
'''
if old2 in s: s=s.replace(old2,new2,1)
elif '_qb_comp_rate' not in s: raise SystemExit('sim anchor missing')
s=s.replace('''                        if rng.random() < 0.021:
''','''                        if rng.random() < _qb_int_rate:
''',1)
old3='''                        catch_prob = float(np.clip(0.70 * _hist_catch + 0.30 * 0.64, 0.42, 0.88))
'''
new3='''                        # Blend receiver catch history with the QB's own completion rate.
                        catch_prob = float(np.clip(0.60 * _hist_catch + 0.40 * _qb_comp_rate, 0.42, 0.88))
'''
if old3 in s: s=s.replace(old3,new3,1)
old4='''                            _yard_mean = float(np.clip(_hist_ypr, 5.0, 20.0))
'''
new4='''                            # Reconcile receiver YPR with QB historical YPA/completion rate.
                            _qb_ypc = _qb_ypa / max(_qb_comp_rate, 0.01)
                            _yard_mean = float(np.clip(0.65 * _hist_ypr + 0.35 * _qb_ypc, 5.0, 20.0))
'''
if old4 in s: s=s.replace(old4,new4,1)
old5='''                            td_prob = float(np.clip((0.80 * _hist_rec_td_rate + 0.20 * 0.035) * score_env + max(yards - 20.0, 0.0) * 0.001, 0.006, 0.18))
'''
new5='''                            # A completed pass can score according to both the receiver's
                            # target TD rate and the QB's historical passing-TD rate.
                            _qb_td_per_completion = _qb_td_rate / max(_qb_comp_rate, 0.01)
                            td_prob = float(np.clip((0.55 * _hist_rec_td_rate / max(catch_prob, 0.01) + 0.45 * _qb_td_per_completion) * score_env + max(yards - 20.0, 0.0) * 0.001, 0.006, 0.20))
'''
if old5 in s: s=s.replace(old5,new5,1)
# Soften RB historical YPC toward league baseline; prevents small-sample RB efficiency inflation.
old6='''                            _ypc = float(np.clip(_ypc, 2.5, 7.0))
'''
new6='''                            _ypc = float(np.clip(0.75 * _ypc + 0.25 * 4.25, 2.8, 6.2))
'''
# only RB branch; there is one exact line after prior patch
if old6 in s: s=s.replace(old6,new6,1)
p.write_text(s)
print('Calibrated FanDuel PBP QB efficiency, TD/INT rates, and RB efficiency')
