"""Lightweight NBA starting-five status refresh, independent of point projections."""
import json
from urllib.request import urlopen
from simmah_nba_projections import team_key, player_key
from simmah_nba_game_strip import explicit_true


def parse_lineup_status(players,day,pairs):
    expected={tuple(p) for p in pairs};result={}
    for p in players:
        team=team_key(p.get('team',{}).get('abbr',''))
        opponent=team_key(p.get('opponent',{}).get('team',''))
        if str(p.get('game',{}).get('dateTime',''))[:10]!=day or (team,opponent) not in expected:
            raise ValueError('NBA lineup source date or matchup differs from uploaded slate')
        key=player_key(p.get('firstName','')+' '+p.get('lastName',''),team)
        if not key[0] or key in result:raise ValueError('Duplicate or missing NBA lineup player')
        lineup=p.get('lineup') or {}
        result[key]={'Game Start':p.get('game',{}).get('dateTime'),'Expected Starter':explicit_true(lineup.get('slot')),
                     'Starter Confirmed':explicit_true(lineup.get('isConfirmed',False))}
    if not result:raise ValueError('No NBA lineup records returned')
    return result


def download_lineup_status(slate_id,day,pairs):
    if not str(slate_id).isdigit():raise ValueError('Numeric RotoWire slate ID required')
    with urlopen('https://www.rotowire.com/daily/nba/api/players.php?slateID='+str(slate_id),timeout=8) as response:
        players=json.load(response)
    import time
    return {'players':parse_lineup_status(players,day,pairs),'checked_at':time.time()}


def render_live_strip(st,pool,markets,slate_id,day,fallback_time=None):
    import time
    from simmah_nba_game_strip import render_game_strip
    from simmah_nba_confirmed import current_confirmed_pool
    pairs=tuple(sorted({(team_key(r.Team),team_key(r.Opponent)) for r in pool.itertuples()}))
    @st.fragment(run_every='10s')
    def draw():
        view,response=current_confirmed_pool(st,pool,day,pairs)
        checked=response.get('checked_at',fallback_time);source_ok=not response['stale']
        if response.get('pending'):st.caption('Checking RotoWire starting lineups…')
        elif response.get('issue'):st.caption('RotoWire lineup check: '+response['issue'])
        scope=(day,pairs)
        if source_ok:
            observe_lineup_change(st.session_state,scope,lineup_snapshot(view),lineup_snapshot(pool))
        pending=bool(st.session_state.get('nba_lineup_updates_found'))
        st.markdown(refresh_button_style(pending),unsafe_allow_html=True)
        if pending:st.caption('Starting lineup changed. Use the red REFRESH button to apply the update.')
        render_game_strip(st,view,markets,checked)
    draw()


def lineup_snapshot(pool):
    from simmah_nba_game_strip import team_lineup
    teams=sorted(set(pool['Team'].map(team_key)))
    return tuple((team,detail['status'],tuple(sorted(n.strip().casefold() for n in detail['starters'])))
                 for team in teams for detail in [team_lineup(pool,team)])


def observe_lineup_change(state,scope,snapshot,applied_snapshot=None):
    record=state.get('nba_lineup_monitor')
    if not record or record['scope']!=scope:
        record={'scope':scope,'applied':snapshot if applied_snapshot is None else applied_snapshot,'pending':False}
    record['latest']=snapshot
    record['pending']=record['pending'] or snapshot!=record['applied']
    state['nba_lineup_monitor']=record
    state['nba_lineup_updates_found']=record['pending']
    return record['pending']


def acknowledge_lineup_refresh(state):
    state.pop('nba_lineup_monitor',None)
    state['nba_lineup_updates_found']=False


def refresh_button_style(pending):
    background='#d62828' if pending else '#0b2034'
    border='#d62828' if pending else '#24516b'
    return ('<style>.st-key-sticky_projection_bar button {'
            f'background-color:{background} !important;border-color:{border} !important;color:#ffffff !important;'
            '}</style>')


