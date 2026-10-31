"""Team-split and QB/receiver constraints for six-player single-game rosters."""
OPTIONS = ['Any / All', '3–3', '4–2', '5–1']


def control_keys(platform, mode):
    prefix = 'single_stacks_' + platform + '_' + mode
    return prefix + '_splits', prefix + '_qb_receiver'


def render_controls(st, platform, mode):
    splits, qb = control_keys(platform, mode)
    st.multiselect('Team stacks in MY lineups', OPTIONS, default=[OPTIONS[0]], key=splits,
        help='Any / All allows every legal team split. Otherwise accept any selected split, in either direction. Both teams remain required. Applies to new builds.')
    st.checkbox('Pair each QB with a same-team WR/TE', value=False, key=qb,
        help='Every selected quarterback needs at least one same-team wide receiver or tight end. Applies to new builds.')


def matches(chosen, lookup, splits=(), qb_receiver=False):
    rows = [lookup.get(str(name), {}) for name in chosen.values()]
    teams = [str(row.get('Team', '')).strip().upper() for row in rows]
    if len(rows) != 6 or any(not t for t in teams) or len(set(teams)) != 2:
        return False
    counts = sorted(teams.count(t) for t in set(teams))
    if splits and OPTIONS[0] not in splits:
        allowed = {'3–3': [3, 3], '4–2': [2, 4], '5–1': [1, 5]}
        if not any(counts == allowed.get(split) for split in splits):
            return False
    if qb_receiver:
        for row, team in zip(rows, teams):
            pos = set(str(row.get('Position', '')).upper().split('/'))
            if 'QB' in pos and not any(t == team and set(str(r.get('Position', '')).upper().split('/')) & {'WR', 'TE'} for r, t in zip(rows, teams)):
                return False
    return True


def selected_validator(st, platform, mode, lookup):
    splits, qb = control_keys(platform, mode)
    selected = tuple(st.session_state.get(splits, [OPTIONS[0]]))
    pair_qb = bool(st.session_state.get(qb, False))
    return lambda chosen: matches(chosen, lookup, selected, pair_qb)
