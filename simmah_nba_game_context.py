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


def restore_saved_game_metadata(pool,previous,day):
    """Recover display metadata only, with exact salary IDs and dated games.

    Never copy projections, minutes, ownership or injury eligibility. A saved
    starting five is only a last-known expectation, never fresh confirmation.
    """
    import pandas as pd
    from simmah_nba_game_strip import game_start,explicit_true
    if not isinstance(previous,pd.DataFrame) or previous.empty:return pool
    if not {'Player ID','Team','Opponent','Game Start'}<=set(previous):return pool
    if previous['Player ID'].astype(str).duplicated().any():return pool
    if set(previous['Player ID'].astype(str))!=set(pool['Player ID'].astype(str)):return pool
    source=previous.set_index(previous['Player ID'].astype(str));view=pool.copy()
    changed=False
    for index,row in view.iterrows():
        old=source.loc[str(row['Player ID'])]
        if (team_key(old['Team']),team_key(old['Opponent']))!=(team_key(row['Team']),team_key(row['Opponent'])):continue
        start=game_start([old['Game Start']])
        if start is None or start.date().isoformat()!=day:continue
        for column in ('Game Start','Game Total','Team Implied Points'):
            value=old.get(column)
            if column=='Game Start':
                current_start=game_start([row.get(column)])
                valid=current_start is not None and current_start.date().isoformat()==day
            else:
                try:valid=math.isfinite(float(row.get(column))) and float(row.get(column))>0
                except (TypeError,ValueError):valid=False
                try:
                    number=float(value)
                    if not math.isfinite(number) or not ((100<number<400) if column=='Game Total' else (40<number<200)):continue
                except (TypeError,ValueError):continue
            if not valid:
                view.at[index,column]=value;changed=True
        if 'Expected Starter' in old and explicit_true(old['Expected Starter']):
            # Restore only when the current provider has supplied no expected
            # starters for this team. Compute this from the original pool.
            current=pool[pool['Team'].map(team_key)==team_key(row['Team'])]
            if 'Expected Starter' not in current or not current['Expected Starter'].map(explicit_true).any():
                view.at[index,'Expected Starter']=True
                view.at[index,'Starter Confirmed']=False
                view.at[index,'Lineup Status Stale']=True
    if changed:view.attrs['saved_game_metadata_restored']=True
    return view


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

