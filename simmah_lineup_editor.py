"""Manual, validated edits to the assigned entry portfolio."""
import hashlib
import json
import pandas as pd
from simmah_injury_display import injury_frame, injury_label


def swap_player(portfolio, pool, slots, row_number, slot, replacement, platform, validator=None):
    result = portfolio.copy().reset_index(drop=True)
    lookup = pool.drop_duplicates('Name').set_index('Name').to_dict('index')
    if slot not in slots or replacement not in lookup:
        raise ValueError('Choose an eligible roster slot and player.')
    row = result.iloc[row_number].to_dict()
    row[slot] = replacement
    names = [str(row[s]) for s in slots]
    if len(set(names)) != len(names):
        raise ValueError('A player cannot appear twice in one lineup.')
    single = 'Captain' in slots or 'MVP' in slots
    total = points = 0.
    for s, name in zip(slots, names):
        player = lookup.get(name)
        if player is None:
            raise ValueError('A player is no longer in the eligible pool.')
        projection = pd.to_numeric(player.get('Projection'), errors='coerce')
        if pd.isna(projection) or projection <= 0 or str(player.get('Injury Status', '')).lower() in {'out', 'o'} or bool(player.get('Fade', False)):
            raise ValueError('Players must have a positive projection and cannot be Out or faded.')
        pos = str(player.get('Position', '')).upper().replace('DEF', 'DST').split('/')
        pos = {'DST' if p == 'D' else p for p in pos}
        allowed = {'RB', 'WR', 'TE'} if s == 'FLEX' else {'DST'} if s in {'D', 'DST'} else {s.rstrip('123')}
        if not single and not pos.intersection(allowed):
            raise ValueError(f'{name} is not eligible for {s}.')
        multiplier = 1.5 if s in {'Captain', 'MVP'} else 1.
        total += float(player['Salary']) * multiplier
        points += float(projection) * multiplier
    cap = 60000 if platform == 'FanDuel' else 50000
    if total > cap:
        raise ValueError(f'The lineup exceeds the ${cap:,} salary cap.')
    teams = [str(lookup[n].get('Team', '')) for n in names]
    if single and len(set(teams)) < 2:
        raise ValueError('A single-game lineup must include both teams.')
    if not single:
        limit = 4 if platform == 'FanDuel' else 8
        if max(teams.count(t) for t in set(teams)) > limit:
            raise ValueError('The lineup exceeds the team limit.')
        for name in names:
            p = lookup[name]
            if str(p.get('Position', '')).upper() in {'D', 'DST', 'DEF'}:
                if any(str(lookup[n].get('Team', '')) == str(p.get('Opponent', '')) for n in names if n != name):
                    raise ValueError('Offensive players cannot face your defense.')
    if validator and not validator(row):
        raise ValueError('The swap violates your selected lineup rules.')
    for i, other in result.iterrows():
        if i == row_number:
            continue
        same = (other[slots[0]] == row[slots[0]] and set(other[slots[1:]]) == set(names[1:])) if single else set(other[slots]) == set(names)
        if same:
            raise ValueError('The swap would duplicate another assigned lineup.')
    locked = {name for name, p in lookup.items() if p.get('Lock') is True}
    if not locked.issubset(names):
        raise ValueError('The swap would remove a locked player.')
    result.loc[row_number, slot] = replacement
    # Remove evaluation metrics until the caller evaluates the changed portfolio.
    result = result[[c for c in result if c in slots or c in {'Salary', 'ProjectedPoints', 'Total Sim Pts', 'Locked'}]].copy()
    result.loc[row_number, 'Salary'] = total
    for col in ('ProjectedPoints', 'Total Sim Pts'):
        if col in result:
            result.loc[row_number, col] = points
    return result


def render_editor(st, portfolio, pool, slots, platform, mode, contest, validator=None):
    fingerprint = json.dumps([platform, mode, portfolio[slots].astype(str).values.tolist(), pool[['Name', 'Salary']].astype(str).values.tolist(), contest], sort_keys=True, default=str)
    key = 'manual_lineups_' + hashlib.sha256(fingerprint.encode()).hexdigest()[:20]
    current = st.session_state.get(key, portfolio).copy()
    st.subheader('My lineups')
    st.session_state['display_injury_statuses'] = dict(zip(pool['Name'].astype(str), pool.get('Injury Status', pd.Series('Active', index=pool.index))))
    st.dataframe(injury_frame(st, current[[c for c in [*slots, 'Salary', 'ProjectedPoints', 'Total Sim Pts'] if c in current]]), hide_index=True, use_container_width=True)
    statuses = st.session_state.get('display_injury_statuses', {})
    with st.form(key + '_form'):
        number = st.selectbox('Lineup', range(len(current)), format_func=lambda n: f'Lineup {n + 1}')
        slot = st.selectbox('Player slot', slots)
        player = st.selectbox('Replacement player', sorted(pool['Name'].astype(str).unique()), format_func=lambda name: injury_label(name, statuses))
        apply = st.form_submit_button('Apply player swap')
        if apply:
            try:
                current = swap_player(current, pool, slots, number, slot, player, platform, validator)
                st.session_state[key] = current
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.caption('Swaps update your assigned entries and their export. Download your updated entry file from Build after editing. Manual swaps may change portfolio exposures.')
    return current
