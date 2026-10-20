"""Public DFF NBA projections, restricted to the uploaded slate date and games."""
from datetime import date
from html.parser import HTMLParser
from urllib.request import Request, urlopen
import math
import re
import pandas as pd


def slate_date(filename):
    match = re.search(r'NBA-(\d{4}-\d{2}-\d{2})-', filename)
    if not match:
        raise ValueError('NBA slate date is missing from the original filename')
    return date.fromisoformat(match[1]).isoformat()


class ProjectionTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []

    def handle_starttag(self, tag, attrs):
        row = dict(attrs)
        if tag == 'tr' and 'data-ppg_proj' in row:
            self.rows.append(row)


def player_key(name, team):
    # Site feeds omit generational suffixes inconsistently (e.g. Philon Jr.).
    import unicodedata
    name=''.join(c for c in unicodedata.normalize('NFKD',str(name)) if not unicodedata.combining(c))
    name=re.sub(r'\s+(?:jr\.?|sr\.?|ii|iii|iv)$','',name.strip(),flags=re.I)
    return (' '.join(name.casefold().split()),team_key(team))


def positive(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, TypeError):
        return None


def parse_dff(html, day, pool):
    parser = ProjectionTable()
    parser.feed(html)
    games = {(str(r.Team).upper(), str(r.Opponent).upper()) for r in pool.itertuples()}
    values = {}
    for row in parser.rows:
        team, opp = row.get('data-team','').upper(), row.get('data-opp','').upper()
        if row.get('data-start_date') != day or (team, opp) not in games:
            continue
        value = positive(row.get('data-ppg_proj'))
        if value is None:
            continue
        key = player_key(row.get('data-name',''), team)
        if key in values and values[key] != value:
            raise ValueError('Conflicting NBA projections for the same player')
        values[key] = value
    if not values:
        raise ValueError('No positive DFF projections match the NBA slate date and games')
    return values


def download_dff(day, pool, platform='FanDuel'):
    day = date.fromisoformat(day).isoformat()
    path='fanduel/' if platform=='FanDuel' else ''
    url = f'https://www.dailyfantasyfuel.com/nba/projections/{path}{day}/'
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=15) as response:
        return parse_dff(response.read().decode('utf-8'), day, pool)


def apply_projections(pool, automatic, uploaded=None):
    result = pool.copy()
    overrides = {}
    if uploaded is not None:
        if not {'Player ID','Projection'} <= set(uploaded.columns):
            raise ValueError('Projection CSV requires Player ID and Projection columns')
        if uploaded['Player ID'].astype(str).duplicated().any():
            raise ValueError('Projection CSV contains duplicate Player IDs')
        known = set(pool['Player ID'].astype(str))
        if not set(uploaded['Player ID'].astype(str)) <= known:
            raise ValueError('Projection CSV contains players from another NBA slate')
        overrides = dict(zip(uploaded['Player ID'].astype(str), uploaded['Projection']))
    projections, sources = [], []
    for row in result.itertuples(index=False, name=None):
        player = dict(zip(result.columns, row))
        pid = str(player['Player ID'])
        if pid in overrides:
            value, source = positive(overrides[pid]), 'Uploaded CSV'
        else:
            value = automatic.get(player_key(player['Name'], player['Team']))
            value, source = positive(value), 'DFF'
        projections.append(value)
        sources.append(source if value is not None or pid in overrides else 'Missing')
    result['Projection'] = projections
    result['Projection Source'] = sources
    result['Eligible'] = result['Projection'].notna() & ~result['Injury Status'].isin(['Out','O','OUT'])
    return result


def team_key(value):
    value = str(value).upper().strip()
    return {'NYK':'NY','SAS':'SA','GSW':'GS','NOP':'NO'}.get(value,value)


def select_rotowire_slate(payload, day, pool, platform='FanDuel'):
    expected = {(team_key(r.Team),team_key(r.Opponent)) for r in pool.itertuples()}
    expected |= {(b,a) for a,b in expected}
    matches = []
    for slate in payload.get('slates',[]):
        if slate.get('contestType') != ('Classic' if platform=='DraftKings' else 'Full Roster') or slate.get('startDateOnly') != day:
            continue
        games = [payload.get('games',{}).get(str(g)) for g in slate.get('games',[])]
        if not games or any(not g or str(g.get('gameDate',''))[:10]!=day for g in games):
            continue
        pairs = {(team_key(g['homeTeamCode']),team_key(g['visitTeamCode'])) for g in games}
        pairs |= {(b,a) for a,b in pairs}
        if pairs == expected:
            matches.append(slate)
    if len(matches) != 1:
        raise ValueError('No unique RotoWire NBA slate matches date, games and format')
    return matches[0]


def parse_rotowire(players, projections, day, pool):
    if projections.get('access') is not True or projections.get('source') != 'RotoWire':
        raise ValueError('RotoWire NBA projection access unavailable')
    pts = {str(r['slateID']):positive(r.get('pts')) for r in projections.get('projections',[])}
    allowed = {(team_key(r.Team),team_key(r.Opponent)) for r in pool.itertuples()}
    values, details = {}, {}
    for player in players:
        team = team_key(player.get('team',{}).get('abbr',''))
        opp = team_key(player.get('opponent',{}).get('team',''))
        if str(player.get('game',{}).get('dateTime',''))[:10] != day or (team,opp) not in allowed:
            raise ValueError('RotoWire NBA player date or matchup does not match uploaded slate')
        key = player_key(player.get('firstName','')+' '+player.get('lastName',''),team)
        value = pts.get(str(player.get('slateID')))
        if value is not None:
            values[key] = value
        minutes = positive(player.get('minutes'))
        if minutes is not None and minutes > 48:
            minutes = None
        try:
            rostership = float(player.get('rostership'))
            if not math.isfinite(rostership) or not 0 <= rostership <= 100:
                rostership = None
        except (TypeError, ValueError):
            rostership = None
        season = player.get('stats',{}).get('season',{})
        role_details = {}
        try:
            historical_minutes = float(season.get('minutes'))
            if not math.isfinite(historical_minutes) or historical_minutes <= 0:
                raise ValueError('No historical minutes')
            for role,stat in [('Shot','fga'),('Assist','ast'),('Rebound','reb'),('Steal','stl'),('Block','blk')]:
                rate = float(season[stat])/historical_minutes
                if not math.isfinite(rate) or rate < 0:raise ValueError('Invalid role rate')
                role_details['Historical '+role+' Rate'] = rate
        except (ValueError,TypeError,KeyError):
            role_details = {}
        lineup = player.get('lineup') or {}
        details[key] = {**role_details, 'Game Start':player.get('game',{}).get('dateTime'), 'RotoWire RST % (unverified)':rostership, 'Projected Minutes':minutes, 'Minutes Source':'RotoWire' if minutes else 'Missing',
            'RotoWire Injury':player.get('injuryStatus') or 'Active',
            'Expected Starter':lineup.get('slot'),
            'Starter Confirmed':str(lineup.get('isConfirmed',False)).strip().casefold() in {'true','yes','1'},
            'Game Total':positive(player.get('odds',{}).get('overUnder')),
            'Team Implied Points':positive(player.get('odds',{}).get('impliedPts'))}
    return values, details


def download_rotowire(day, pool, platform='FanDuel'):
    import json
    base = 'https://www.rotowire.com/daily/nba/api/'
    def get(endpoint):
        with urlopen(base+endpoint,timeout=15) as response:
            return json.load(response)
    slate = select_rotowire_slate(get('slate-list.php?siteID='+('1' if platform=='DraftKings' else '2')),day,pool,platform=platform)
    sid = str(slate['slateID'])
    players = get('players.php?slateID='+sid)
    projections = get('projections.php?slateID='+sid+'&projSource=RotoWire')
    values, details = parse_rotowire(players,projections,day,pool)
    return values, details, sid
