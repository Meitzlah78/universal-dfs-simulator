"""Input audit, not an accuracy benchmark. No unavailable participation -> zero."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import urllib.request
import numpy as np
import pandas as pd
from scripts.expand_minutes_evidence_offline import player_key
from simmah_nba_verified_minutes_offline import age_shrink


def run(root, metadata, output):
    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    f = pd.read_csv(root/'independent-minutes-benchmark/site_predictions.csv', dtype={'game_id':str,'package':str})
    u = pd.read_csv(root/'independent-minutes-benchmark/unmatched_forecasts.csv', dtype={'game_id':str,'package':str})
    history = json.loads((root/'independent-minutes-benchmark/history_rows.json').read_text())
    seasons = {r['game_id']:r for r in json.loads(Path(metadata).read_text())}
    contexts = json.loads((root/'independent-minutes-context/team_context.json').read_text())
    def fetch(day):
        path = output/('official_lineups_'+day+'.json')
        if path.exists():
            return json.loads(path.read_text())
        url = 'https://stats.nba.com/js/data/leaders/00_daily_lineups_'+day.replace('-','')+'.json'
        try:
            request = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Accept':'application/json','Referer':'https://www.nba.com/'})
            data = json.load(urllib.request.urlopen(request, timeout=12))
            result = {'date':day,'source':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'games':data.get('games',[])}
            path.write_text(json.dumps(result, indent=2))
            return result
        except Exception as exc:
            return {'date':day,'error':type(exc).__name__}
    with ThreadPoolExecutor(max_workers=3) as pool:
        feeds = list(pool.map(fetch, sorted(f.date.unique())))
    official = {}
    for feed in feeds:
        for game in feed.get('games',[]):
            for side in ('homeTeam','awayTeam'):
                team = game.get(side,{})
                for player in team.get('players',[]):
                    name = player.get('playerName') or ' '.join([player.get('firstName',''),player.get('lastName','')])
                    official[(feed['date'],player_key(name,team['teamAbbreviation']))] = dict(player, evidence_source=feed['source'], evidence_retrieved_at=feed['retrieved_at'], evidence_game_id=game.get('gameId'))
    # Inspect original raw flags: the old flattened history discarded these.
    raw = {}
    for path in (root/'simmah-nba-clock/data/nba_pbp').glob('*/*.json.gz'):
        game = json.loads(gzip.decompress(path.read_bytes()))
        for team in game['boxscore']['players']:
            for stats in team['statistics']:
                for p in stats['athletes']:
                    key=player_key(p['athlete']['displayName'],team['team']['abbreviation'])
                    raw[(str(game['event_id']),key)]=p
    participation = {'played':0,'confirmed_dnp':0,'unknown_zero':0,'missing_raw':0}
    for row in history:
        p=raw.get((row['game_id'],tuple(row['key'])))
        state=('missing_raw' if p is None else 'played' if row['minutes']>0 else 'confirmed_dnp' if p.get('didNotPlay') is True else 'unknown_zero')
        participation[state]+=1
    roster_audit=[];sensitivities=[]
    groupcols=['package','game_id','team']
    for group,g in f.groupby(groupcols):
        extra=u[(u.package==group[0])&(u.game_id==group[1])&(u.team==group[2])]
        day=g.date.iloc[0];capture=g.capture.iloc[0]
        names=list(g.name)+list(extra.name)
        for name in names:
            key=player_key(name,group[2]);p=official.get((day,key))
            own=[r for r in history if tuple(r['key'])==key and r['date']<day and pd.Timestamp(r['completed_at'])<pd.Timestamp(capture)]
            reg=[r for r in own if seasons.get(r['game_id'],{}).get('usable') and seasons[r['game_id']].get('season_type_slug')=='regular-season']
            latest=max((r['completed_at'] for r in own),default=None)
            matched=name in set(g.name)
            roster_audit.append({'package':group[0],'game_id':group[1],'team':group[2],'date':day,'name':name,
                'scored':matched,'history_n':len(own),'regular_history_n':len(reg),
                'latest_history_age_days':(pd.Timestamp(capture)-pd.Timestamp(latest)).total_seconds()/86400 if latest else None,
                'official_row_found':bool(p),'official_roster_status':p.get('rosterStatus') if p else None,
                'official_position':p.get('position') if p else None,'official_timestamp':p.get('timestamp') if p else None,
                'official_source':p.get('evidence_source') if p else None,'official_retrieved_at':p.get('evidence_retrieved_at') if p else None,
                'official_game_id':p.get('evidence_game_id') if p else None,
                'eligibility_certified':False,'role_prior_certified':False,
                'blocker':'No verified timezone/validity interval and game-eligibility semantics for official row' if p else 'No official dated matching row recovered'})
            if not matched or key[0] in {'cormac ryan','kam jones'}:
                for prior in (4.,12.,24.,32.):
                    for elapsed in (0,14,28,56):
                        at=(pd.Timestamp(capture)+pd.Timedelta(days=elapsed)).isoformat()
                        e=age_shrink(reg,prior,at)
                        sensitivities.append({'package':group[0],'game_id':group[1],'team':group[2],'name':name,
                            'regular_history_n':len(reg),'extra_days_without_new_evidence':elapsed,'assumed_role_prior':prior,**e})
    pd.DataFrame(roster_audit).to_csv(output/'roster_metadata_audit.csv',index=False)
    pd.DataFrame(sensitivities).to_csv(output/'unknown_participation_sensitivity.csv',index=False)
    short=[c for c in contexts if len(c['historical_core_out'])>=2]
    (output/'short_handed_contexts.json').write_text(json.dumps(short,indent=2))
    a=pd.DataFrame(roster_audit)
    summary={'available_player_snapshots':len(a),'unknown_actual_snapshots':int((~a.scored).sum()),
        'official_rows_matched':int(a.official_row_found.sum()),'official_roster_status_counts':a.official_roster_status.fillna('missing').value_counts().to_dict(),'certified_eligibility':0,'certified_current_role_priors':0,
        'reason_not_certified':'Official timestamps have no UTC offset; rosterStatus Active and row validity are not yet certified as game-eligibility evidence at saved capture.',
        'historical_participation':participation,'team_snapshots':len(contexts),'two_or_more_historical_core_out_snapshots':len(short),
        'unique_two_or_more_core_out_team_games':len({(c['game_id'],c['team']) for c in short}),
        'source_errors':[feed for feed in feeds if 'error' in feed],
        'accuracy_backtest':'blocked: no certified current-role priors/eligibility; do not silently drop unsupported snapshots',
        'sensitivity_warning':'Role priors 4/12/24/32 are illustrative sensitivity inputs, not fitted forecasts or actual labels.'}
    (output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('metadata');p.add_argument('output');a=p.parse_args();run(a.root,a.metadata,a.output)
