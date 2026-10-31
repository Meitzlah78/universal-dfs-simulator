"""Read public RotoWire optimizer projections with exact platform/slate guards."""
import json
import math
import re
from datetime import date
from urllib.parse import urlencode
from urllib.request import urlopen

BASE = 'https://www.rotowire.com/daily/nfl/api/'
FORMATS = {'DraftKings Classic':(1,'Classic'), 'DraftKings Showdown':(1,'Showdown'),
           'FanDuel Full Roster':(2,'Full Roster'), 'FanDuel Single Game':(2,'SingleGame')}


def team_key(value):
    value = str(value).strip().upper()
    return {'WSH':'WAS','LA':'LAR','JAC':'JAX'}.get(value,value)


def name_key(value):
    value = re.sub(r'\s+(jr|sr|ii|iii|iv|v)\.?$', '', str(value).strip().lower())
    return re.sub('[^a-z0-9]', '', value)


def select_slate(payload, platform, teams, dates):
    _, mode = FORMATS[platform]
    expected = {team_key(t) for t in teams}
    if len(expected)<2 or not dates:
        raise ValueError('Salary-slate teams/date required')
    candidates=[]
    for slate in payload.get('slates',[]):
        if slate.get('contestType') != mode:
            continue
        games = [payload.get('games',{}).get(str(g)) for g in slate.get('games',[])]
        if not games or any(not g for g in games):
            continue
        actual_teams = {team_key(g[k]) for g in games for k in ['homeTeamCode','visitTeamCode']}
        actual_dates = {str(g.get('gameDate',''))[:10] for g in games}
        if actual_teams == expected and actual_dates == set(dates):
            candidates.append(slate)
    if len(candidates)!=1:
        raise ValueError('No unique RotoWire slate matches the salary teams, dates and format')
    return candidates[0]


def parse_projections(players, payload, teams, dates):
    if not isinstance(payload,dict) or payload.get('access') is not True or payload.get('source')!='RotoWire':
        raise ValueError('RotoWire projection access unavailable')
    if not isinstance(players,list) or not isinstance(payload.get('projections'),list):
        raise ValueError('Unexpected RotoWire response')
    values={}
    for row in payload['projections']:
        try:
            v=float(row['pts'])
        except (KeyError,TypeError,ValueError):
            continue
        if math.isfinite(v) and v>0:
            values[str(row['slateID'])]=v
    output={}
    for player in players:
        team=team_key(player.get('team',{}).get('abbr',''))
        day=str(player.get('game',{}).get('dateTime',''))[:10]
        if team not in {team_key(t) for t in teams} or day not in dates:
            raise ValueError('RotoWire player belongs to another slate')
        v=values.get(str(player.get('slateID')))
        if v is None:
            continue
        name=(str(player.get('firstName',''))+' '+str(player.get('lastName',''))).strip()
        aliases=[name]
        if player.get('isTeamDefense'):
            aliases += [player.get('team',{}).get('nickname',''),team]
        for alias in aliases:
            key=name_key(alias)
            if key:
                if key in output and output[key] != v:
                    raise ValueError('Conflicting duplicate RotoWire player projection')
                output[key]=v
    if not output:
        raise ValueError('No positive RotoWire projections')
    return output


def download(platform, teams, dates, opener=urlopen):
    site,_=FORMATS[platform]
    def get(endpoint,params):
        with opener(BASE+endpoint+'?'+urlencode(params),timeout=12) as response:
            return json.load(response)
    slate=select_slate(get('slate-list.php',{'siteID':site}),platform,teams,dates)
    sid=slate['slateID']
    players=get('players.php',{'slateID':sid})
    projections=get('projections.php',{'slateID':sid,'projSource':'RotoWire'})
    return parse_projections(players,projections,teams,dates),str(sid)


def salary_dates(frame):
    """Only explicit salary-file game dates; never infer a date from player stats."""
    dates=set()
    for col in frame.columns:
        if str(col).lower().replace(' ','') not in {'gameinfo','game','starttime','kickoff','weatherkickoff'}:
            continue
        for value in frame[col].dropna().astype(str):
            for raw in re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b',value):
                try:
                    if '/' in raw:
                        m,d,y=map(int,raw.split('/'));dates.add(date(y,m,d).isoformat())
                    else:
                        dates.add(date.fromisoformat(raw).isoformat())
                except ValueError:
                    continue
    return tuple(sorted(dates))
