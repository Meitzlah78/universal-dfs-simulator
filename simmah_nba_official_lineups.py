"""Dated NBA.com starting fives; blank-position roster rows are never starters."""
from datetime import date
import json
import time
from urllib.request import Request,urlopen
from simmah_nba_lineup_cache import LineupPageCache
from simmah_nba_projections import team_key,player_key


def parse_daily_lineups(payload,day,pairs):
    date.fromisoformat(day)
    expected={tuple(sorted(map(team_key,p))) for p in pairs}
    values={};seen=set()
    for game in payload.get('games',[]):
        home=game.get('homeTeam',{});away=game.get('awayTeam',{})
        pair=tuple(sorted((team_key(home.get('teamAbbreviation','')),team_key(away.get('teamAbbreviation','')))))
        if pair not in expected:continue
        if pair in seen:raise ValueError('Duplicate NBA.com matchup')
        seen.add(pair)
        for team in (home,away):
            abbr=team_key(team.get('teamAbbreviation',''))
            # Full roster/availability rows may also be labelled Confirmed.
            starters=[p for p in team.get('players',[]) if p.get('position') in {'PG','SG','SF','PF','C'}]
            if len(starters)!=5 or len({p['position'] for p in starters})!=5:continue
            statuses={str(p.get('lineupStatus','')).casefold() for p in starters}
            if statuses not in ({'expected'},{'confirmed'}):continue
            if any(str(p.get('timestamp',''))[:10]!=day for p in starters):continue
            if any(p.get('rosterStatus')!='Active' or str(p.get('teamId'))!=str(team.get('teamId')) for p in starters):continue
            ids=[str(p.get('personId','')) for p in starters]
            keys=[player_key(p.get('playerName',''),abbr) for p in starters]
            if len(set(ids))!=5 or '' in ids or len(set(keys))!=5 or any(not key[0] for key in keys):continue
            for key in keys:
                values[key]={'Expected Starter':True,'Starter Confirmed':statuses=={'confirmed'}}
    if not values:raise ValueError('No complete dated NBA.com starting five for this slate')
    return values


def download_daily_lineups(day):
    date.fromisoformat(day)
    request=Request('https://stats.nba.com/js/data/leaders/00_daily_lineups_'+day.replace('-','')+'.json',
                    headers={'User-Agent':'Mozilla/5.0','Accept':'application/json','Referer':'https://www.nba.com/'})
    with urlopen(request,timeout=8) as response:payload=json.load(response)
    return {'payload':payload,'checked_at':time.time()}


def _download(day):
    result=download_daily_lineups(day)
    return {'players':result['payload'],'checked_at':result['checked_at']}


_cache=LineupPageCache(_download)


def cached_lineups(day,pairs,force=False):
    result=_cache.get(day,force=force)
    if result.get('error'):raise ValueError(result['error'])
    if not result.get('players'):return {'pending':True,'stale':True,'players':{},'source':'NBA.com daily lineups'}
    return {**result,'players':parse_daily_lineups(result['players'],day,pairs),
            'source':'NBA.com daily lineups'}


def request_refresh(day):
    _cache.get(day,force=True)
