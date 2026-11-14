"""Audit capture timing and backfill earlier-game role priors, without roster hindsight."""
import argparse
import gzip
import json
from pathlib import Path
import pandas as pd
from scripts.expand_minutes_evidence_offline import player_key
from simmah_nba_role_prior_offline import training_examples,current_prior


def run(root, metadata_path, out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=True)
    metadata={r['game_id']:r for r in json.loads(Path(metadata_path).read_text())}
    rows=[];excluded=[]
    for path in (root/'simmah-nba-clock/data/nba_pbp').glob('*/*.json.gz'):
        d=json.loads(gzip.decompress(path.read_bytes()));gid=str(d['event_id'])
        if not metadata.get(gid,{}).get('usable') or metadata[gid].get('season_type_slug')!='regular-season':
            continue
        events=d['events'];period=max(e.get('period',{}).get('number',0) for e in events)
        clocks=[pd.Timestamp(e['wallclock']) for e in events if e.get('wallclock')]
        if period!=4 or not clocks:
            continue
        started=min(clocks).isoformat();completed=max(clocks).isoformat()
        for t in d['boxscore']['players']:
            for g in t['statistics']:
                for p in g['athletes']:
                    key=player_key(p['athlete']['displayName'],t['team']['abbreviation'])
                    values=dict(zip(g['labels'],p.get('stats',[])))
                    try:
                        value=float(values.get('MIN'))
                    except (TypeError,ValueError):
                        value=0. if p.get('didNotPlay') is True else None
                    state='played' if value is not None and value>0 else 'confirmed_dnp' if value==0 and p.get('didNotPlay') is True else 'unknown'
                    if state=='unknown' or type(p.get('starter')) is not bool or value is None or not 0<=value<=48:
                        excluded.append({'game_id':gid,'key':key,'reason':'unknown participation / missing starter / invalid regulation minutes'});continue
                    rows.append({'key':key,'game_id':gid,'date':d['date'],'game_started_at':started,'completed_at':completed,
                        'minutes':value,'started':p['starter'],'participation':state,'source':str(path.name),
                        'season_verified':True,'season_source':metadata[gid]['season_source'],
                        'season_type':'regular','season_id':metadata[gid]['season_id']})
    examples=training_examples(rows)
    f=pd.read_csv(root/'independent-minutes-benchmark/site_predictions.csv',dtype={'game_id':str,'package':str})
    u=pd.read_csv(root/'independent-minutes-benchmark/unmatched_forecasts.csv',dtype={'game_id':str,'package':str})
    priors=[]
    for group,g in f.groupby(['package','game_id','team']):
        extra=u[(u.package==group[0])&(u.game_id==group[1])&(u.team==group[2])]
        for name in list(g.name)+list(extra.name):
            key=player_key(name,group[2])
            prior=current_prior(rows,examples,key,g.date.iloc[0],g.capture.iloc[0])
            priors.append({'package':group[0],'game_id':group[1],'team':group[2],'name':name,'capture':g.capture.iloc[0],**prior})
    pd.DataFrame(priors).to_csv(out/'role_priors.csv',index=False)
    (out/'role_training_examples.json').write_text(json.dumps(examples))
    # Clock hypothesis audit is diagnostic only: neither timezone is certified.
    stale=pd.read_csv('docs/offline/verified_minutes/input_audit/stale_player_cases.csv',dtype={'game_id':str,'package':str})
    captures=f.groupby('package').capture.first().to_dict();timing=[]
    for _,r in stale.iterrows():
        cap=pd.Timestamp(captures[r.package]);raw=pd.Timestamp(r.official_timestamp)
        utc=raw.tz_localize('UTC');eastern=raw.tz_localize('America/New_York').tz_convert('UTC')
        timing.append({'package':r.package,'game_id':r.game_id,'name':r['name'],'capture':cap.isoformat(),
            'source_timestamp':r.official_timestamp,'if_UTC_delta_minutes':(utc-cap).total_seconds()/60,
            'if_Eastern_delta_minutes':(eastern-cap).total_seconds()/60,
            'too_late_under_both_hypotheses':bool(utc>cap and eastern>cap),
            'certified_asof':False,'source':r.official_source})
    pd.DataFrame(timing).to_csv(out/'capture_timing.csv',index=False)
    # Postgame boxscores cannot be used as historical eligible pools.
    coverage=[{'game_id':gid,'date':next(r['date'] for r in rows if r['game_id']==gid) if any(r['game_id']==gid for r in rows) else None,
        'verified_season':True,'verified_pregame_eligible_pool':False,'allocation_evaluable':False,
        'allocation_conflict':None,'blocked_reason':'No certified pregame eligible-pool snapshot; postgame participants are not a substitute'}
        for gid,m in metadata.items() if m.get('usable') and m.get('season_type_slug')=='regular-season']
    pd.DataFrame(coverage).to_csv(out/'game_conflict_coverage.csv',index=False)
    supported=[p for p in priors if p['supported']]
    summary={'regular_history_games':len({r['game_id'] for r in rows}),'regular_history_rows':len(rows),
        'excluded_history_records':len(excluded),'chronological_role_training_examples':len(examples),
        'player_snapshots':len(priors),'supported_historical_role_priors':len(supported),
        'unsupported_role_priors':len(priors)-len(supported),
        'no_role_history':sum(p.get('reason')=='insufficient earlier regular-season role history' for p in priors),
        'insufficient_role_training':sum(p.get('reason')=='insufficient earlier same-role training outcomes' for p in priors),
        'timestamp_player_cases':len(timing),'too_late_under_both_hypotheses':sum(t['too_late_under_both_hypotheses'] for t in timing),
        'regular_game_denominator':len(coverage),'allocation_evaluable_games':0,'input_blocked_games':len(coverage),
        'allocation_conflict_rate':None,'input_blocked_rate':1.,
        'accuracy_residuals':'not evaluable: no certified capture-time eligible pools; independent historical role priors do not certify availability',
        'protocol':'Fixed trailing5 starter rate >=0.5 after >=3 explicit earlier observations; same-role earlier mean with >=20 training labels. Development evidence only; not tuned to the single injury-heavy team-game.'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('metadata');p.add_argument('out');a=p.parse_args();run(a.root,a.metadata,a.out)
