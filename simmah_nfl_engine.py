"""Vectorized NFL regulation-game stat simulation shared by all DFS formats.

Each array column is an independently generated game. Events are shared by the
passer, receiver, opposing defense and scoreboard before DFS scoring is applied.
Rates are model assumptions/history inputs, not learned from contest uploads.
"""
import numpy as np

ENGINE_VERSION = 'shared-nfl-v4-confirmed-qb-roles'
STAT_KEYS = (
    'passing_yards', 'passing_tds', 'interceptions', 'rushing_yards',
    'rushing_tds', 'receiving_yards', 'receiving_tds', 'receptions',
    'fumbles_lost', 'two_point_conversions', 'sacks', 'def_interceptions',
    'fumble_recoveries', 'defensive_tds', 'safeties', 'blocked_kicks',
    'points_allowed', 'yards_allowed', 'fg_under_40', 'fg_40_49',
    'fg_50_plus', 'extra_points_made',
)


def simulate_stat_lines(pool, roles, rng, n, correlation_strength=1.0, progress=None, return_diagnostics=False, weather_by_team=None, projection_inputs=None, scoring_platform="FanDuel"):
    """Return name -> stat arrays; no point scaling, clipping or bootstrapping."""
    from simmah_weather import weather_factors
    weather_by_team = weather_by_team or {}
    projection_inputs = projection_inputs or {}
    reception_points = 1. if str(scoring_platform).casefold() in {"draftkings","dk"} else .5
    n = int(n)
    if n < 1:
        raise ValueError('Simulation count must be positive')
    rows = pool.to_dict('records')
    def team_key(value):
        key = str(value or '').upper().strip()
        return {'JAC': 'JAX', 'WSH': 'WAS', 'OAK': 'LV', 'SD': 'LAC', 'LA': 'LAR'}.get(key, key)
    for row in rows:
        row['Team'] = team_key(row.get('Team', ''))
        row['Opponent'] = team_key(row.get('Opponent', ''))
    stats = {str(row['Name']): {key: np.zeros(n, dtype=np.float32) for key in STAT_KEYS} for row in rows}
    # Event masks compare compact integer IDs instead of Python name objects.
    # Keep player order and RNG calls unchanged for identical seeded outcomes.
    player_ids = {name: i for i, name in enumerate(stats)}
    player_names = list(stats)
    selection_codes = {}
    by_team = {}
    for row in rows:
        team = str(row.get('Team', '')).upper().strip()
        if team:
            by_team.setdefault(team, []).append(row)
    strength = float(np.clip(correlation_strength, 0, 1))
    indices = np.arange(n)

    def position(row):
        return str(row.get('Position', '')).upper().split('/')[0].strip()

    def add(name, key, idx, amount=1):
        if name and len(idx):
            stats[name][key][idx] += amount

    def profile(team):
        players = by_team.get(team, [])
        def best(pos):
            options = [r for r in players if position(r) in pos]
            return str(max(options, key=lambda r: float(r.get('Projection', 0)))['Name']) if options else None
        projected_qbs=[r for r in players if position(r)=='QB' and float(r.get('Projection',0))>0]
        if len({str(r['Name']) for r in projected_qbs})>1:
            raise ValueError('Multiple projected quarterbacks for '+team+
                '; confirm the starter before simulation: '+', '.join(str(r['Name']) for r in projected_qbs))
        qb = best({'QB'})
        receivers = [r for r in players if position(r) in {'WR', 'TE', 'RB'}]
        runners = [r for r in players if position(r) == 'RB']
        def weights(group, field, history_weight):
            projection = np.array([max(float(r.get('Projection', 0)), .01) for r in group])
            # Convert total fantasy projections to the relevant opportunity
            # budget. RB receiving/rushing shares use their individual history;
            # an RB's entire rushing projection must not become target weight.
            for i,r in enumerate(group):
                role=roles.get(str(r['Name']),{})
                if position(r)=='RB':
                    receiving=.1*role.get('rec_yards',0)+reception_points*role.get('receptions',0)+6*role.get('rec_tds',0)
                    rushing=.1*role.get('rush_yards',0)+6*role.get('rush_tds',0)
                    rec_share=np.clip(receiving/max(receiving+rushing,1e-6),.03,.85) if receiving+rushing>0 else .25
                    projection[i]*=rec_share if field=='targets' else 1-rec_share
                if field=='targets':
                    rec=role.get('receptions',0);targets=role.get('targets',0)
                    catch=np.clip(rec/targets,.35,.88) if targets else .64
                    ypr=np.clip(role.get('rec_yards',0)/max(rec,1e-6),5,20) if rec else 11.2
                    points_per_target=catch*(reception_points+.1*ypr)+6*role.get('rec_tds',0)/max(targets,1)
                    projection[i]/=max(points_per_target,.2)
                else:
                    carries=role.get('carries',0)
                    ypc=np.clip(role.get('rush_yards',0)/max(carries,1e-6),2,8.5) if carries else 4.35
                    projection[i]/=max(.1*ypc+6*role.get('rush_tds',0)/max(carries,1),.1)
            history = np.array([max(roles.get(str(r['Name']), {}).get(field, 0), 0) for r in group])
            if not len(projection):
                return np.array([])
            p = projection / projection.sum()
            return history_weight * history / history.sum() + (1-history_weight) * p if history.sum() else p
        rec_w = weights(receivers, 'targets', .25)
        rush_w = weights(runners, 'carries', .25)
        if len(rec_w):
            rec_w *= np.array([projection_inputs.get(str(r['Name']),{}).get('opportunity',1.) for r in receivers])
            rec_w /= rec_w.sum()
        if len(rush_w):
            rush_w *= np.array([projection_inputs.get(str(r['Name']),{}).get('opportunity',1.) for r in runners])
            rush_w /= rush_w.sum()
        qb_role = roles.get(qb, {})
        qa = qb_role.get('pass_attempts', 0)
        carries = sum(roles.get(str(r['Name']), {}).get('carries', 0) for r in runners)
        qb_carries = qb_role.get('carries', 0)
        pass_rate = np.clip(qa / max(qa + carries + qb_carries, 1), .44, .70) if qa >= 15 else .58
        qb_run_share = np.clip(qb_carries / max(carries + qb_carries, 1), 0, .40)
        # Include QB carries in the finite rushing pool.
        if qb and (qb_run_share > 0 or not runners):
            runners = runners + [next(r for r in players if str(r['Name']) == qb)]
            rush_w = np.append(rush_w * (1-qb_run_share), qb_run_share if len(rush_w) else 1.)
        return dict(qb=qb, receivers=[str(r['Name']) for r in receivers], rec_w=rec_w,
                    runners=[str(r['Name']) for r in runners], rush_w=rush_w,
                    kicker=best({'K'}), defense=best({'D', 'DST', 'DEF'}),
                    pass_rate=pass_rate, role=qb_role, pass_gain=float(projection_inputs.get(qb,{}).get('pass_gain',1.)))

    def select(names, weights, count):
        if not names or not count:
            return np.array([], dtype=np.int32)
        key = tuple(names)
        if key not in selection_codes:
            selection_codes[key] = np.asarray([player_ids[name] for name in names], dtype=np.int32)
        return selection_codes[key][rng.choice(len(names), count, p=weights)]

    diagnostics = {}
    seen = set()
    for team, team_players in by_team.items():
        if team in seen:
            continue
        opp = next((str(r.get('Opponent', '')).strip().upper() for r in team_players
                    if str(r.get('Opponent', '')).strip().upper() not in {'', 'NAN', 'NONE', '—', '-'}), '')
        # Even an unlisted opponent consumes possession/time, without inventing
        # DFS players or attaching stats to another team in the pool.
        opp = opp if opp and opp != team else '__opponent_' + team
        teams = [team, opp]
        seen.update(teams)
        if progress is not None:
            progress(min(.99, len(seen.intersection(by_team)) / max(len(by_team), 1)),
                     f"Simulating {n:,} independent outcomes: {team} vs {opp}")
        profiles = [profile(t) for t in teams]
        game_weather = weather_by_team.get(team) or weather_by_team.get(opp) or {}
        factors = weather_factors(game_weather)
        counters = {key: np.zeros((2, n), dtype=np.int32) for key in (
            'offensive_tds', 'defensive_tds', 'safeties', 'pat_attempts', 'pat_made',
            'two_attempts', 'two_made', 'fg_attempts', 'fg_made', 'plays',
        )}
        points = np.zeros((2, n))
        chargeable = np.zeros((2, n))
        yards_total = np.zeros((2, n))
        clock = np.full(n, 3600.)
        possession = rng.integers(0, 2, n)
        field = np.full(n, 25.)  # yards from the offense's own goal line
        down = np.ones(n, dtype=int)
        to_go = np.full(n, 10.)
        pace = np.clip(1 + strength * rng.normal(0, .09, n), .80, 1.22)
        environment = np.clip(1 + strength * rng.normal(0, .10, n), .75, 1.30)

        def switch(idx, new_field):
            possession[idx] = 1 - possession[idx]
            field[idx] = np.clip(new_field, 1, 99)
            down[idx] = 1
            to_go[idx] = np.minimum(10, 100-field[idx])

        def conversion(side, idx):
            """One PAT or two-point attempt per TD; conversions aren't normal plays."""
            if not len(idx):
                return
            p = profiles[side]
            two = rng.random(len(idx)) < .097
            two_idx, kick_idx = idx[two], idx[~two]
            counters['two_attempts'][side, two_idx] += 1
            counters['pat_attempts'][side, kick_idx] += 1
            xp_made = kick_idx[rng.random(len(kick_idx)) < .9468 * factors['kick_accuracy']]
            counters['pat_made'][side, xp_made] += 1
            points[side, xp_made] += 1
            chargeable[side, xp_made] += 1
            add(p['kicker'], 'extra_points_made', xp_made)
            pass_two = rng.random(len(two_idx)) < .55
            for passing, attempts, chance in [(True, two_idx[pass_two], .4437), (False, two_idx[~pass_two], .5466)]:
                success = attempts[rng.random(len(attempts)) < chance]
                counters['two_made'][side, success] += 1
                points[side, success] += 2
                chargeable[side, success] += 2
                names = p['receivers'] if passing else p['runners']
                weights = p['rec_w'] if passing else p['rush_w']
                if passing:
                    add(p['qb'], 'two_point_conversions', success)
                selected = select(names, weights, len(success))
                for name in names:
                    add(name, 'two_point_conversions', success[selected == player_ids[name]])

        # Clock always decreases by >= 12 seconds, so this bound covers regulation.
        for _play in range(301):
            alive = clock > 0
            if not alive.any():
                break
            active_possession = possession.copy()
            for side in (0, 1):
                idx = indices[alive & (active_possession == side)]
                if not len(idx):
                    continue
                p, defense = profiles[side], profiles[1-side]['defense']
                counters['plays'][side, idx] += 1
                clock[idx] -= np.clip(rng.normal(28, 6, len(idx)) / pace[idx], 12, 45)
                # Fourth down: field goal within range, otherwise punt. Near the
                # goal/late while trailing, allow an offensive fourth-down play.
                trailing = points[side, idx] < points[1-side, idx]
                go = (down[idx] == 4) & ((field[idx] > 95) | ((clock[idx] < 180) & trailing))
                fourth = idx[(down[idx] >= 4) & ~go]
                if len(fourth):
                    fg = fourth[field[fourth] >= 60]
                    punt = fourth[field[fourth] < 60]
                    distance = 117-field[fg]
                    probability = np.clip(.97 - .005*np.maximum(distance-30, 0) - .009*np.maximum(distance-45, 0), .35, .98)
                    made = rng.random(len(fg)) < probability * factors['kick_accuracy']
                    made_idx = fg[made]
                    counters['fg_attempts'][side, fg] += 1
                    counters['fg_made'][side, made_idx] += 1
                    points[side, made_idx] += 3
                    chargeable[side, made_idx] += 3
                    for key, mask in [('fg_under_40', distance < 40), ('fg_40_49', (distance >= 40) & (distance < 50)), ('fg_50_plus', distance >= 50)]:
                        add(p['kicker'], key, fg[made & mask])
                    new_field = np.where(made, 25, np.minimum(80, 100-(field[fg]-7)))
                    switch(fg, new_field)
                    punt_field = np.clip(100-(field[punt]+rng.normal(43, 9, len(punt))), 1, 99)
                    punt_field = np.where(punt_field < 10, 20, punt_field)
                    switch(punt, punt_field)
                idx = idx[~np.isin(idx, fourth)]
                if not len(idx):
                    continue
                margin = points[side, idx] - points[1-side, idx]
                pass_rate = np.clip(p['pass_rate'] - factors['rush_share'] - .004 * margin, .35, .80)
                passing = rng.random(len(idx)) < pass_rate
                gain = np.zeros(len(idx))
                carrier = np.full(len(idx), -1, dtype=np.int32)
                interception = np.zeros(len(idx), dtype=bool)
                sack = np.zeros(len(idx), dtype=bool)
                caught = np.zeros(len(idx), dtype=bool)
                if passing.any():
                    sack = passing & (rng.random(len(idx)) < .065)
                    gain[sack] = -np.clip(rng.normal(6, 3, sack.sum()), 1, 15)
                    add(defense, 'sacks', idx[sack])
                    role = p['role']; attempts = role.get('pass_attempts', 0)
                    int_rate = np.clip(role.get('interceptions', 0)/max(attempts, 1), .006, .05) if attempts else .021
                    interception = passing & ~sack & (rng.random(len(idx)) < int_rate)
                    add(p['qb'], 'interceptions', idx[interception])
                    add(defense, 'def_interceptions', idx[interception])
                    throw = passing & ~sack & ~interception
                    selected = select(p['receivers'], p['rec_w'], int(throw.sum()))
                    if not p['receivers']:
                        # Missing salary-pool players still participate in the
                        # football game; do not fabricate DFS player records.
                        virtual = np.flatnonzero(throw & (rng.random(len(idx)) < .64 * factors['completion'] * p['pass_gain']**.20))
                        caught[virtual] = True
                        gain[virtual] = np.clip(rng.gamma(1.5, 11.2/1.5, len(virtual))*environment[idx[virtual]]*factors['pass_yards']*p['pass_gain']**.80, 0, 85)
                    if len(selected):
                        carrier[throw] = selected
                        for name in p['receivers']:
                            loc = np.flatnonzero(throw & (carrier == player_ids[name]))
                            role = roles.get(name, {}); targets = role.get('targets', 0); rec = role.get('receptions', 0)
                            qb_comp = np.clip(p['role'].get('completions', 0)/max(attempts, 1), .52, .76) if attempts else .64
                            chance = np.clip((.6*(rec/targets if targets else .64)+.4*qb_comp) * factors['completion'] * p['pass_gain']**.20, .35, .88)
                            complete = loc[rng.random(len(loc)) < chance]
                            caught[complete] = True
                            ypr = np.clip(role.get('rec_yards', 0)/rec, 5, 20) if rec else 11.2
                            gain[complete] = np.clip(rng.gamma(1.5, np.clip(ypr*projection_inputs.get(name,{}).get('skill_gain',1.)*p['pass_gain']**.80,3,24)/1.5, len(complete))*environment[idx[complete]]*factors['pass_yards'], 0, 85)
                running = ~passing
                selected = select(p['runners'], p['rush_w'], int(running.sum()))
                if not p['runners']:
                    gain[running] = np.clip(rng.normal(4.35, 5.5, int(running.sum())), -5, 65)
                if len(selected):
                    carrier[running] = selected
                    for name in p['runners']:
                        loc = np.flatnonzero(running & (carrier == player_ids[name]))
                        role = roles.get(name, {}); carries = role.get('carries', 0)
                        ypc = np.clip(role.get('rush_yards', 0)/carries, 2, 8.5) if carries else 4.35
                        gain[loc] = np.clip(rng.normal(np.clip(ypc*projection_inputs.get(name,{}).get('skill_gain',1.),1,8.5), 5.5, len(loc))*np.sqrt(environment[idx[loc]]), -5, 65)
                gain = np.clip(gain, -field[idx], 100-field[idx])
                for name in p['receivers']:
                    loc = np.flatnonzero(caught & (carrier == player_ids[name]))
                    add(name, 'receptions', idx[loc])
                    add(name, 'receiving_yards', idx[loc], gain[loc])
                    add(p['qb'], 'passing_yards', idx[loc], gain[loc])
                for name in p['runners']:
                    loc = np.flatnonzero(running & (carrier == player_ids[name]))
                    add(name, 'rushing_yards', idx[loc], gain[loc])
                yards_total[side, idx] += gain
                # Only the actual ball carrier can lose a fumble.
                carrier[sack] = player_ids.get(p['qb'], -1)
                fumble = ~interception & ((caught | running | sack) & (carrier >= 0)) & (rng.random(len(idx)) < .0064)
                for code in np.unique(carrier[fumble]):
                    add(player_names[code], 'fumbles_lost', idx[fumble & (carrier == code)])
                add(defense, 'fumble_recoveries', idx[fumble])
                touchdown = (field[idx] + gain >= 100) & ~interception & ~fumble
                td_idx = idx[touchdown]
                for name in p['receivers']:
                    add(name, 'receiving_tds', idx[touchdown & caught & (carrier == player_ids[name])])
                add(p['qb'], 'passing_tds', idx[touchdown & caught])
                for name in p['runners']:
                    add(name, 'rushing_tds', idx[touchdown & running & (carrier == player_ids[name])])
                counters['offensive_tds'][side, td_idx] += 1
                points[side, td_idx] += 6
                chargeable[side, td_idx] += 6
                conversion(side, td_idx)
                safety = (field[idx] + gain <= 0) & ~interception & ~fumble
                safe_idx = idx[safety]
                add(defense, 'safeties', safe_idx)
                counters['safeties'][1-side, safe_idx] += 1
                points[1-side, safe_idx] += 2
                turnover = interception | fumble
                turn_idx = idx[turnover]
                return_td = rng.random(len(turn_idx)) < .08
                return_idx = turn_idx[return_td]
                add(defense, 'defensive_tds', return_idx)
                counters['defensive_tds'][1-side, return_idx] += 1
                points[1-side, return_idx] += 6  # defensive TDs excluded from points allowed
                conversion(1-side, return_idx)
                ordinary = ~(touchdown | safety | turnover)
                live_idx = idx[ordinary]
                g = gain[ordinary]
                first = g >= to_go[live_idx]
                field[live_idx] += g
                down[live_idx] = np.where(first, 1, down[live_idx]+1)
                to_go[live_idx] = np.where(first, np.minimum(10, 100-field[live_idx]), to_go[live_idx]-g)
                failed = live_idx[down[live_idx] > 4]
                switch(failed, 100-field[failed])
                switch(td_idx, 25)
                switch(safe_idx, 35)
                switch(turn_idx[~return_td], 100-(field[turn_idx[~return_td]]+gain[turnover][~return_td]))
                # After a defensive TD, the original offense receives the kickoff.
                field[return_idx] = 25; down[return_idx] = 1; to_go[return_idx] = 10
        if return_diagnostics:
            for side, name in enumerate(teams):
                diagnostics[name] = {key: values[side].copy() for key, values in counters.items()}
                diagnostics[name]['points'] = points[side].copy()
                diagnostics[name]['chargeable'] = chargeable[side].copy()
                diagnostics[name]['clock_remaining'] = clock.copy()
        for side, p in enumerate(profiles):
            if p['defense']:
                stats[p['defense']]['points_allowed'] = chargeable[1-side].copy()
                stats[p['defense']]['yards_allowed'] = yards_total[1-side].copy()
    return (stats, diagnostics) if return_diagnostics else stats
