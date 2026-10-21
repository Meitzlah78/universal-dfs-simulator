"""On-demand ESPN NBA box scores converted to site fantasy points.

Observed points are display-only: never added to full-game simulation outcomes.
"""
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import urlopen
import pandas as pd
from simmah_nba_projections import team_key,player_key
from simmah_nba_scoring import score_nba

BASE='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/'


def eastern_day(stamp):
    value=datetime.fromisoformat(str(stamp).replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('Source game date lacks timezone')
    return value.astimezone(ZoneInfo('America/New_York')).date().isoformat()


def stat_number(value):
    if isinstance(value,bool):raise ValueError('Invalid live statistic')
    number=float(value)
    if not math.isfinite(number) or number<0 or number!=int(number):raise ValueError('Invalid live statistic')
    return number


def parse_boxscore(payload,game_id,day,pair,platform):
    header=payload['header']
    if str(header['id'])!=str(game_id):raise ValueError('Live box-score game ID mismatch')
    game=header['competitions'][0]
    teams={team_key(c['team']['abbreviation']) for c in game['competitors']}
    if eastern_day(game['date'])!=day or teams!=set(pair):raise ValueError('Live box-score date or matchup mismatch')
    status=game['status'];state=status['type'].get('state')
    if state=='pre':return []
    final=status['type'].get('completed') is True and state=='post'
    if not final and state!='in':raise ValueError('Unsupported game status; live scoring unavailable')
    rows=[];seen=set()
    for group in payload.get('boxscore',{}).get('players',[]):
        team=team_key(group['team']['abbreviation'])
        if team not in teams:raise ValueError('Unexpected box-score team')
        for table in group.get('statistics',[]):
            labels=table.get('labels',[])
            for athlete in table.get('athletes',[]):
                person=athlete.get('athlete',{});pid=str(person.get('id',''))
                name=person.get('displayName','')
                key=player_key(name,team)
                if not pid or not name or key in seen:raise ValueError('Missing or ambiguous box-score player')
                seen.add(key)
                stats=athlete.get('stats',[])
                values=dict(zip(labels,stats)) if len(stats)==len(labels) else {}
                fields={'points':'PTS','rebounds':'REB','assists':'AST','steals':'STL','blocks':'BLK','turnovers':'TO'}
                try:
                    if not values and final and athlete.get('didNotPlay') is True:
                        scored={field:0. for field in fields};scored['threes']=0.
                    else:
                        scored={field:stat_number(values[label]) for field,label in fields.items()}
                        made_attempted=str(values['3PT']).split('-')
                        if len(made_attempted)!=2:raise ValueError('Missing made-three statistic')
                        scored['threes']=stat_number(made_attempted[0])
                        if scored['threes']>stat_number(made_attempted[1]):raise ValueError('Invalid three-point line')
                    points=float(score_nba(platform,**scored));issue=''
                except (ValueError,TypeError,KeyError):
                    points=None;issue='Incomplete statistics; not treated as zero'
                rows.append({'Source Player ID':pid,'Name':name,'Team':team,'Opponent':next(iter(teams-{team})),
                    'Game ID':str(game_id),'Game Status':'FINAL' if final else 'LIVE',
                    'Period':status.get('period'),'Clock':status.get('displayClock',''),
                    'Fantasy Points':points,'Issue':issue,'Source':'ESPN box score',
                    'Box Stats':scored if points is not None else None})
    return rows


def download_live(day,pairs,platform):
    datetime.strptime(day,'%Y-%m-%d')
    def read(url):
        with urlopen(url,timeout=8) as response:return json.load(response)
    scoreboard=read(BASE+'scoreboard?dates='+day.replace('-','')+'&limit=100')
    expected={tuple(sorted(p)) for p in pairs};found=set();rows=[];issues=[]
    for event in scoreboard.get('events',[]):
        if eastern_day(event['date'])!=day:continue
        game=event['competitions'][0]
        pair=tuple(sorted(team_key(c['team']['abbreviation']) for c in game['competitors']))
        if pair not in expected:continue
        if pair in found:raise ValueError('Ambiguous scoreboard matchup')
        found.add(pair)
        if event['status']['type'].get('state')=='pre':
            issues.append(' @ '.join(pair)+': not started');continue
        game_id=str(event['id'])
        if not game_id.isdigit():raise ValueError('Invalid source game ID')
        try:rows.extend(parse_boxscore(read(BASE+'summary?event='+game_id),game_id,day,pair,platform))
        except (ValueError,KeyError,OSError,TypeError) as exc:issues.append(' @ '.join(pair)+': box score unavailable ('+type(exc).__name__+')')
    issues.extend(' @ '.join(pair)+': not found on dated scoreboard' for pair in sorted(expected-found))
    return {'rows':rows,'issues':issues,'fetched_at':datetime.now(ZoneInfo('America/New_York')).isoformat()}


def match_pool(pool,rows):
    buckets={}
    for row in rows:buckets.setdefault(player_key(row['Name'],row['Team']),[]).append(row)
    counts=pool.apply(lambda r:player_key(r['Name'],r['Team']),axis=1).value_counts()
    output=[]
    for _,player in pool.iterrows():
        key=player_key(player['Name'],player['Team']);matches=buckets.get(key,[])
        row={'Player ID':str(player['Player ID']),'Name':player['Name'],'Team':player['Team'],
             'Fantasy Points':None,'Game Status':'UNMATCHED','Issue':'No verified matching box-score row'}
        if len(matches)==1 and counts[key]==1 and team_key(matches[0]['Opponent'])==team_key(player['Opponent']):
            row.update({k:v for k,v in matches[0].items() if k not in {'Name','Team'}})
            row['Match']='Unique name + team + dated matchup (not a site-ID join)'
        output.append(row)
    return pd.DataFrame(output)


def render_live_points(st,pool,day,platform):
    with st.expander('Live fantasy points — '+platform):
        st.caption('Observed box-score points only. These do not change projections or late-swap simulations. Source updates and stat corrections may lag the contest site.')
        key='nba_live_points_refresh'
        st.session_state.setdefault('_slate_action_keys',set()).add(key)
        pairs=tuple(sorted({tuple(sorted((team_key(r.Team),team_key(r.Opponent)))) for r in pool.itertuples()}))
        identity=(day,platform,pairs,tuple(pool['Player ID'].astype(str)))
        if st.button('REFRESH LIVE FANTASY POINTS',key=key):
            try:
                result=st.cache_data(ttl=20,show_spinner=False,max_entries=8)(download_live)(day,pairs,platform)
                st.session_state['nba_live_points_result']=(identity,result)
                save_live_snapshot(st.session_state,pool,day,platform,result)
            except (ValueError,KeyError,OSError,TypeError):st.warning('Live box-score feed unavailable. No scores were substituted.')
        saved=st.session_state.get('nba_live_points_result')
        if saved and saved[0]==identity:
            result=saved[1];st.caption('Last successful fetch: '+result['fetched_at'])
            for issue in result['issues']:st.caption(issue)
            view=match_pool(pool,result['rows'])
            from simmah_nba_player_display import player_labels
            view['Name']=view['Player ID'].map(player_labels(pool))
            st.dataframe(view,hide_index=True,width='stretch',column_config={'Name':st.column_config.TextColumn('Player',pinned=True)})
            st.caption('Blank fantasy points mean unavailable or unmatched, never an assumed zero. Matching uses unique name, team, opponent and slate date; verify against your contest site.')
        history=st.session_state.get('nba_live_score_history',[])
        if history:
            from simmah_slate_workspaces import workspace_download_button
            st.caption(f'{len(history)} distinct box-score snapshots saved with this slate. Live snapshots are not training labels. Final results are available for later validation; no model parameters are changed.')
            payload={'schema':1,'snapshots':history,'latest_final':st.session_state.get('nba_final_score_history',{})}
            workspace_download_button(st,'EXPORT SAVED LIVE / FINAL RESULTS',json.dumps(payload,indent=2,allow_nan=False).encode(),
                'Simmah_NBA_Live_Results.json','application/json',key='nba_live_results_export',on_click='ignore')


def save_live_snapshot(state,pool,day,platform,result):
    """Archive observations separately from pregame predictions and model fitting."""
    import hashlib
    rows=match_pool(pool,result['rows'])
    records=json.loads(rows.to_json(orient='records'))
    content={'date':day,'platform':platform,'players':records,'issues':result['issues']}
    fingerprint=hashlib.sha256(json.dumps(content,sort_keys=True,allow_nan=False).encode()).hexdigest()
    history=state.setdefault('nba_live_score_history',[])
    if any(item['fingerprint']==fingerprint for item in history):return False
    snapshot={**content,'fingerprint':fingerprint,'fetched_at':result['fetched_at'],
              'purpose':'Observed outcomes only; not a pregame forecast or automatic model update'}
    history.append(snapshot)
    final=state.setdefault('nba_final_score_history',{})
    for row in records:
        if row.get('Game Status')=='FINAL' and row.get('Fantasy Points') is not None and not row.get('Issue'):
            key='|'.join((day,platform,str(row['Game ID']),row['Player ID']))
            final[key]={**row,'date':day,'platform':platform,'fetched_at':result['fetched_at'],
                        'fingerprint':fingerprint,'provisional_source_final':True}
    return True
