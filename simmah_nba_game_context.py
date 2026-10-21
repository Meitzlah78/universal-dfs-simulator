"""NBA schedule/market metadata independent of projection access and DFS site."""
import json
import math
from datetime import date,datetime
from urllib.request import urlopen
from zoneinfo import ZoneInfo
from simmah_nba_projections import team_key


def parse_game_context(payload,day,pairs):
    date.fromisoformat(day)
    expected={tuple(sorted(map(team_key,p))) for p in pairs};found={}
    for game in payload.get('games',{}).values():
        try:stamp=datetime.fromisoformat(str(game.get('gameDate','')).replace('Z','+00:00'))
        except (ValueError,TypeError):continue
        if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=ZoneInfo('America/New_York'))
        if stamp.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=day:continue
        away=team_key(game.get('visitTeamCode',''));home=team_key(game.get('homeTeamCode',''))
        pair=tuple(sorted((away,home)))
        if pair not in expected:continue
        if pair in found:raise ValueError('Duplicate NBA game context matchup')
        item={'start':stamp.isoformat(),'points':{},'total':None}
        try:
            total=float(game['overUnder']);a=float(game['visitTeam']['expectedScore']);h=float(game['homeTeam']['expectedScore'])
            if not all(math.isfinite(v) for v in (total,a,h)) or not 100<total<400 or min(a,h)<=40 or max(a,h)>=200 or abs(a+h-total)>.1:
                raise ValueError('Invalid game market')
            item.update(total=total,points={away:a,home:h})
        except (ValueError,TypeError,KeyError):pass  # A valid schedule can exist without odds.
        found[pair]=item
    return found


def download_game_context(day,pairs):
    # Both sites share NBA games. This endpoint does not require a unique DFS
    # slate or successful player-projection download.
    with urlopen('https://www.rotowire.com/daily/nba/api/slate-list.php?siteID=2',timeout=3) as response:
        return parse_game_context(json.load(response),day,pairs)


def download_game_context_result(day,pairs):
    try:return {'values':download_game_context(day,pairs)}
    except (ValueError,OSError,KeyError,TypeError) as exc:return {'error':str(exc)}


def has_game_context(pool):
    from simmah_nba_markets import extract_markets
    from simmah_nba_game_strip import game_start
    pairs={tuple(sorted((team_key(r.Team),team_key(r.Opponent)))) for r in pool.itertuples()}
    if 'Game Start' not in pool or len(extract_markets(pool))!=len(pairs):return False
    for team in pool['Team'].unique():
        if game_start(pool.loc[pool['Team']==team,'Game Start'].dropna()) is None:return False
    return True


def apply_game_context(pool,context):
    result=pool.copy();result.attrs.update(pool.attrs)
    for i,row in result.iterrows():
        item=context.get(tuple(sorted((team_key(row['Team']),team_key(row['Opponent'])))))
        if item is None:continue
        existing=row.get('Game Start')
        # Preserve the dated salary CSV clock when present.
        if existing is None or str(existing).strip().lower() in {'','nan','none','nat'}:
            result.at[i,'Game Start']=item['start']
        if item['total'] is not None:
            result.at[i,'Game Total']=item['total']
            result.at[i,'Team Implied Points']=item['points'][team_key(row['Team'])]
    return result

