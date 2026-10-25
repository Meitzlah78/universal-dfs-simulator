"""User-lineup game exclusions; opponent and simulation pools stay complete."""
import re
from simmah_weather import team_key


def game_options(pool):
    games = {}
    for row in pool.to_dict('records'):
        team, opponent = team_key(row.get('Team', '')), team_key(row.get('Opponent', ''))
        raw = str(row.get('Game Info') or row.get('Game') or '')
        match = re.search(r'\b([A-Z]{2,3})\s*@\s*([A-Z]{2,3})\b', raw.upper())
        if match:
            away, home = map(team_key, match.groups())
            pair = tuple(sorted((away, home)))
            label = away + ' @ ' + home
        else:
            if not team or not opponent or opponent in {'NAN', 'NONE', '—', '-'} or team == opponent:
                continue
            pair = tuple(sorted((team, opponent)))
            label = ' vs '.join(pair)
        if pair not in games or match:
            games[pair] = label
    return {label: pair for pair, label in sorted(games.items())}


def excluded_player_names(pool, selected_games):
    selected = set(selected_games)
    teams = {team for label, pair in game_options(pool).items() if label in selected for team in pair}
    return set(pool.loc[pool['Team'].map(team_key).isin(teams), 'Name'].astype(str))


def render_game_exclusions(st, pool, platform, mode):
    options = list(game_options(pool))
    key = 'nfl_excluded_games_' + platform + '_' + mode.replace(' ', '_')
    if key in st.session_state:
        valid = [game for game in st.session_state[key] if game in options]
        if valid != st.session_state[key]:
            st.session_state[key] = valid
    selected = st.multiselect('Exclude games from my lineups', options, key=key,
        help='Remove both teams from your candidate builds and assigned entries. Player simulations and opponent lineups still use the full slate.')
    excluded = excluded_player_names(pool, selected)
    if excluded:
        st.caption(f'{len(excluded)} players excluded from your lineups. Run Build to refill candidates; opponents still use the full slate.')
    return excluded
