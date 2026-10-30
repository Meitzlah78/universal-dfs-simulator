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
    name=' '.join(name.casefold().replace('.','').split())
    # Verified provider aliases; retain team in the key and never fuzzy-match.
    name={'alexandre sarr':'alex sarr','gregory jackson':'gg jackson'}.get(name,name)
    return (name,team_key(team))


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
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=6) as response:
        return parse_dff(response.read().decode('utf-8'), day, pool)


class EntriesInProjectionUpload(ValueError):
    pass


def read_projection_upload(data):
    """Validate a projection table before pandas sees a multi-section entries CSV."""
    import csv,io
    rows=csv.reader(io.StringIO(data.decode('utf-8-sig')))
    header=next(rows,[])
    normalized=[cell.strip().casefold() for cell in header]
    if normalized[:2] in (['entry_id','contest_id'],['entry id','contest name']):
        raise EntriesInProjectionUpload('Entries/slate files belong in Slate Setup at the top. This file is not a projections CSV; automatic projections are still being used.')
    if not {'Player ID','Projection'}<=set(header):
        raise ValueError('NBA projection uploads require Player ID and Projection columns')
    if any(row and len(row)!=len(header) for row in rows):
        raise ValueError('Projection CSV rows have inconsistent columns; upload a Player ID / Projection table')
    return pd.read_csv(io.BytesIO(data),dtype={'Player ID':str})


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
    return {'NYK':'NY','SAS':'SA','GSW':'GS','NOP':'NO','PHO':'PHX'}.get(value,value)


def apply_rotowire_projections(pool, values, details, uploaded=None):
    """Use one automatic NBA provider; uploads still override its points."""
    result = apply_projections(pool, values, uploaded)
    result.loc[result['Projection Source'].eq('DFF'), 'Projection Source'] = 'RotoWire'
    for idx, row in result.iterrows():
        news = details.get(player_key(row['Name'], row['Team']), {})
        for col, value in news.items():
            if col=='Game Start' and str(row['Player ID']) in pool.attrs.get('salary_game_starts',{}):
                # Dated site-salary clocks survive missing/changed news metadata.
                result.at[idx,col]=pool.attrs['salary_game_starts'][str(row['Player ID'])]
                continue
            result.at[idx, col] = value
        injury = str(news.get('RotoWire Injury', '')).upper()
        if injury in {'Q', 'QUES', 'QUESTIONABLE'}:
            result.at[idx, 'Injury Status'] = 'Questionable'
        elif injury in {'D', 'DOUBT', 'DOUBTFUL'}:
            result.at[idx, 'Injury Status'] = 'Doubtful'
        elif injury in {'OUT', 'O', 'IR', 'SUSPENDED'}:
            result.at[idx, 'Injury Status'] = 'Out'
            result.at[idx, 'Eligible'] = False
    return result


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


def parse_rotowire(players, projections, day, pool, ownership=None):
    if projections is not None and (projections.get('access') is not True or projections.get('source') != 'RotoWire'):
        raise ValueError('RotoWire NBA projection access unavailable')
    pts = {str(r['slateID']):positive(r.get('pts')) for r in (projections or {}).get('projections',[])}
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
        # Zero is a provider-confirmed non-rotation player, not missing data.
        try:
            minutes = float(player.get('minutes'))
            if not math.isfinite(minutes) or not 0 <= minutes <= 48:minutes = None
        except (TypeError, ValueError):
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
        details[key] = {**role_details, 'Game Start':player.get('game',{}).get('dateTime'), 'RotoWire RST % (unverified)':rostership, 'Projected Minutes':minutes, 'Minutes Source':'RotoWire' if minutes is not None else 'Missing',
            'RotoWire Injury':player.get('injuryStatus') or 'Active',
            'Expected Starter':lineup.get('slot'),
            'Starter Confirmed':str(lineup.get('isConfirmed',False)).strip().casefold() in {'true','yes','1'},
            'Game Total':positive(player.get('odds',{}).get('overUnder')),
            'Team Implied Points':positive(player.get('odds',{}).get('impliedPts'))}
    own={}
    if isinstance(ownership,dict) and ownership.get('access') is True and ownership.get('source')=='RotoWire':
        try:
            for row in ownership['rostership']:
                pid=str(row['slateID']);value=float(row['rst'])
                if pid in own or not math.isfinite(value) or not 0<=value<=100:raise ValueError('Invalid ownership rows')
                own[pid]=value
        except (KeyError,TypeError,ValueError):own={}
    for player in players:
        key=player_key(player.get('firstName','')+' '+player.get('lastName',''),team_key(player.get('team',{}).get('abbr','')))
        if key in details:
            details[key]['RotoWire Projected Own %']=own.get(str(player.get('slateID')))
    return values, details



def select_rotowire_minutes_slate(payload,day,pool,platform='FanDuel'):
    """Select a same-date superset for game-level metadata only."""
    expected={(team_key(r.Team),team_key(r.Opponent)) for r in pool.itertuples()}
    expected|={(b,a) for a,b in expected}
    matches=[]
    for slate in payload.get('slates',[]):
        if slate.get('contestType')!=('Classic' if platform=='DraftKings' else 'Full Roster') or slate.get('startDateOnly')!=day:continue
        games=[payload.get('games',{}).get(str(g)) for g in slate.get('games',[])]
        if not games or any(not g or str(g.get('gameDate',''))[:10]!=day for g in games):continue
        pairs={(team_key(g['homeTeamCode']),team_key(g['visitTeamCode'])) for g in games}
        pairs|={(b,a) for a,b in pairs}
        if expected and expected<=pairs:matches.append((len(games),not bool(slate.get('defaultSlate')),str(slate['slateID']),slate))
    if not matches:raise ValueError('No same-date RotoWire slate covers the uploaded games for minutes')
    return min(matches,key=lambda x:x[:3])[3]

def download_rotowire(day, pool, platform='FanDuel'):
    import json
    from time import monotonic
    deadline=monotonic()+11
    base = 'https://www.rotowire.com/daily/nba/api/'
    def get(endpoint):
        # All primary and reserve lookups share one budget. Optional calls
        # cannot each add another retry cycle to a projection refresh.
        remaining=deadline-monotonic()
        if remaining<=0:raise TimeoutError('RotoWire refresh budget exhausted')
        request = Request(base+endpoint, headers={
            'User-Agent': 'Simmah/1.0 (github.com/Meitzlah78/universal-dfs-simulator)',
            'Accept': 'application/json',
            'Referer': 'https://www.rotowire.com/daily/nba/optimizer.php?site='+platform,
        })
        with urlopen(request,timeout=min(4,remaining)) as response:
            return json.load(response)
    listing=get('slate-list.php?siteID='+('1' if platform=='DraftKings' else '2'))
    try:slate=select_rotowire_slate(listing,day,pool,platform=platform)
    except ValueError:
        slate=select_rotowire_minutes_slate(listing,day,pool,platform=platform)
        sid=str(slate['slateID'])
        allowed={(team_key(r.Team),team_key(r.Opponent)) for r in pool.itertuples()}
        players=[p for p in get('players.php?slateID='+sid)
            if str(p.get('game',{}).get('dateTime',''))[:10]==day
            and (team_key(p.get('team',{}).get('abbr','')),team_key(p.get('opponent',{}).get('team',''))) in allowed]
        _,details=parse_rotowire(players,None,day,pool)
        for row in details.values():
            if row['Projected Minutes'] is not None:row['Minutes Source']='RotoWire same-game minutes (broader slate '+sid+')'
            row['RotoWire RST % (unverified)']=None
            row['RotoWire Projected Own %']=None
        return {},details,sid
    sid = str(slate['slateID'])
    # Minutes/injuries live in players.php and do not depend on access to
    # fantasy projections or ownership. Fetch independent feeds concurrently.
    from concurrent.futures import ThreadPoolExecutor
    other='DraftKings' if platform=='FanDuel' else 'FanDuel'
    other_listing=None
    with ThreadPoolExecutor(max_workers=4) as executor:
        players_job=executor.submit(get,'players.php?slateID='+sid)
        projection_job=executor.submit(get,'projections.php?slateID='+sid+'&projSource=RotoWire')
        ownership_job=executor.submit(get,'rostership.php?slateID='+sid+'&rstSource=RotoWire')
        # Warm the opposite site's slate index during the primary requests.
        # Otherwise a slow primary feed can consume the entire UI budget
        # before the reserve fallback has a chance to look up its game.
        other_listing_job=executor.submit(get,'slate-list.php?siteID='+('1' if other=='DraftKings' else '2')) if 'Name' in pool else None
        players=players_job.result()
        try:projections=projection_job.result()
        except (OSError,ValueError):projections=None
        if projections is not None and (projections.get('access') is not True or projections.get('source')!='RotoWire'):
            projections=None
        try:ownership=ownership_job.result()
        except (OSError,ValueError):ownership=None
        if other_listing_job is not None:
            try:other_listing=other_listing_job.result()
            except (OSError,ValueError):pass
    values, details = parse_rotowire(players,projections,day,pool,ownership)
    missing={player_key(r.Name,r.Team) for r in pool.itertuples()
        if details.get(player_key(r.Name,r.Team),{}).get('Projected Minutes') is None} if 'Name' in pool else set()
    if missing:
        # The same provider can omit a reserve from one site's player feed.
        # Minutes/injuries describe the same game, unlike site scoring/ownership.
        try:
            if other_listing is None:raise ValueError('Opposite-site slate index unavailable')
            # A site's main slate need not contain every game in the other
            # site's slate. Recover missing game-level metadata one game at a
            # time, under the existing shared refresh deadline.
            missing_games={tuple(sorted((team_key(r.Team),team_key(r.Opponent))))
                for r in pool.itertuples() if player_key(r.Name,r.Team) in missing}
            other_feeds={}
            for pair in sorted(missing_games):
                game_pool=pool[pool['Team'].map(team_key).isin(pair)]
                try:
                    other_slate=select_rotowire_minutes_slate(other_listing,day,game_pool,platform=other)
                    other_sid=str(other_slate['slateID'])
                    if other_sid not in other_feeds:
                        other_feeds[other_sid]=get('players.php?slateID='+other_sid)
                    allowed={(team_key(r.Team),team_key(r.Opponent)) for r in game_pool.itertuples()}
                    other_players=[p for p in other_feeds[other_sid]
                        if str(p.get('game',{}).get('dateTime',''))[:10]==day
                        and (team_key(p.get('team',{}).get('abbr','')),team_key(p.get('opponent',{}).get('team',''))) in allowed]
                    _,other_details=parse_rotowire(other_players,None,day,game_pool)
                    for key in missing & set(other_details):
                        row=other_details[key]
                        if row['Projected Minutes'] is None:continue
                        row['Minutes Source']='RotoWire same-game minutes ('+other+' player feed)'
                        if key not in details:
                            row['RotoWire Projected Own %']=None
                            row['RotoWire RST % (unverified)']=None
                            details[key]=row
                        else:
                            # Keep the original site's ownership/news fields.
                            details[key]['Projected Minutes']=row['Projected Minutes']
                            details[key]['Minutes Source']=row['Minutes Source']
                            for column,value in row.items():
                                if column.startswith('Historical ') and column not in details[key]:
                                    details[key][column]=value
                except (ValueError,OSError):
                    continue
        except (ValueError,OSError):
            pass  # Unknown remains unknown; never turn a feed failure into zero.
    return values, details, sid

