"""Read-only development diagnostics: core residuals, allocation ablations, raw gaps."""
import gzip,hashlib,json,sys
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.expand_minutes_evidence_offline import player_key,team_key
from simmah_nba_independent_minutes_offline import forecast_team
from simmah_nba_minutes import allocate_minutes


def raw_athletes(data):
    rows=[]
    for t in data['boxscore']['players']:
        team=team_key(t['team']['abbreviation'])
        for g in t['statistics']:
            for p in g['athletes']:
                stats=dict(zip(g['labels'],p.get('stats',[])));raw=stats.get('MIN');m=None
                try:m=float(raw)
                except (TypeError,ValueError):pass
                rows.append({'team':team,'name':player_key(p['athlete']['displayName'],team)[0],'display_name':p['athlete']['displayName'],'id':str(p['athlete']['id']),'minutes':m,'didNotPlay':p.get('didNotPlay'),'active':p.get('active'),'reason':p.get('reason'),'position':p['athlete'].get('position',{}).get('abbreviation','Unknown')})
    return rows


def classify_raw_gap(name,team,athletes,reference_id=None):
    exact=[a for a in athletes if a['team']==team and a['name']==name]
    same_id=[a for a in athletes if a['team']==team and reference_id and a['id']==reference_id]
    other=[a for a in athletes if a['team']!=team and (a['name']==name or (reference_id and a['id']==reference_id))]
    if len(exact)>1:return 'ambiguous_source_identity',exact
    if not exact and same_id:return 'verified_id_name_key_gap',same_id
    if not exact and other:return 'athlete_found_other_team_only',other
    if not exact:return 'athlete_omitted_from_source_boxscore',[]
    a=exact[0]
    if a['minutes'] is not None and a['minutes']>0:return 'source_positive_minutes',exact
    if a['didNotPlay'] is True and a['minutes'] in [None,0.]:return 'source_explicit_dnp',exact
    return 'source_has_no_explicit_participation_or_dnp',exact


def run(root):
    root=Path(root);out=root/'core-regression-diagnostics';out.mkdir(exist_ok=True)
    source=root/'fresh-vacancy-recency';f=pd.read_csv(source/'chronological_predictions.csv',dtype={'package':str,'game_id':str});allf=pd.read_csv(source/'all_date_predictions.csv',dtype={'package':str,'game_id':str});old=pd.read_csv(root/'independent-minutes-benchmark/site_predictions.csv',dtype={'package':str,'game_id':str});unknown=pd.read_csv(root/'independent-minutes-benchmark/unmatched_forecasts.csv',dtype={'package':str,'game_id':str});history=json.loads((root/'independent-minutes-benchmark/history_rows.json').read_text())
    games={};positions=defaultdict(list);prior_out=defaultdict(list)
    for m in json.loads((root/'independent-minutes-context/team_context.json').read_text()):
        for name in m['historical_core_out']:prior_out[(str(m['game_id']),m['team'],name)].append(m['capture'])
    for p in sorted((root/'simmah-nba-clock/data/nba_pbp').glob('*/*.json.gz')):
        raw=p.read_bytes();d=json.loads(gzip.decompress(raw));gid=str(d['event_id']);clocks=[pd.Timestamp(e['wallclock']) for e in d['events'] if e.get('wallclock')];end=max(clocks) if clocks else None
        games[gid]={'data':d,'athletes':raw_athletes(d),'date':d['date'],'completed_at':end,'opening':min((pd.Timestamp(e['wallclock']) for e in d['events'] if e.get('wallclock') and e.get('period',{}).get('number',0)>=1),default=None),'sha256':hashlib.sha256(raw).hexdigest()}
        if end is not None:
            for a in games[gid]['athletes']:positions[(a['name'],a['team'])].append((d['date'],end,a))
    recovered=[];parity=0.
    for (package,gid,team),g in old.groupby(['package','game_id','team']):
        u=unknown[(unknown.package==package)&(unknown.game_id==gid)&(unknown.team==team)];names=g.name.tolist()+u.name.tolist();roster=[{'name':n,'team':team,'status':'Active'} for n in names];day=g.date.iloc[0];capture=g.capture.iloc[0]
        base=forecast_team(roster,history,day,capture);long=forecast_team(roster,history,day,capture,window=10,half_life=5.);fast=forecast_team(roster,history,day,capture,window=3,half_life=1.)
        braw=np.array([p['raw_minutes'] for p in base]);lraw=np.array([p['raw_minutes'] for p in long]);fraw=np.array([p['raw_minutes'] for p in fast]);core=braw>=28;bench=braw<18
        bonly=allocate_minutes(np.where(bench,fraw,braw)[None,:])[0];conly=allocate_minutes(np.where(core,lraw,braw)[None,:])[0];combined=allocate_minutes(np.where(core,lraw,np.where(bench,fraw,braw))[None,:])[0]
        for i,p in enumerate(base):recovered.append({'package':package,'game_id':gid,'team':team,'name':p['key'][0],'raw_baseline':braw[i],'raw_long':lraw[i],'raw_fast':fraw[i],'raw_recent_minus_long':braw[i]-lraw[i],'bench_only':float(bonly[i]),'core_only':float(conly[i]),'recomputed_tiered':float(combined[i])})
    rec=pd.DataFrame(recovered);f=f.merge(rec,on=['package','game_id','team','name'],validate='one_to_one');parity=float(abs(f.tiered-f.recomputed_tiered).max())
    if parity>1e-8:raise AssertionError('Ablation reconstruction differs from candidate')
    pos=[]
    for r in f.itertuples():
        available=[x for x in positions[r.name,r.team] if x[0]<r.date and x[1]<pd.Timestamp(r.capture)]
        pos.append(max(available,key=lambda x:(x[0],x[1]))[2]['position'] if available else 'Unknown')
    f['prior_position']=pos;f['snapshot_active']=f.availability.astype(str).str.upper()=='ACTIVE';f['minute_shift']=f.tiered-f.baseline;f['error_change']=abs(f.tiered-f.actual_minutes)-abs(f.baseline-f.actual_minutes)
    f['recent_trend']=np.where(f.raw_recent_minus_long>3,'recent_increase_gt3',np.where(f.raw_recent_minus_long< -3,'recent_decrease_gt3','within3'))
    p=f[f.primary&f.original_audit_cohort];core=p[p.provider_tier=='core'];target=core[core.snapshot_active&core.core_vacancy];outside=core[core.snapshot_active&~core.core_vacancy]
    def metrics(g):
        return {'n':len(g),'games':g.game_id.nunique(),'baseline_mae':float(abs(g.baseline-g.actual_minutes).mean()),'tiered_mae':float(abs(g.tiered-g.actual_minutes).mean()),'core_only_mae':float(abs(g.core_only-g.actual_minutes).mean()),'bench_only_mae':float(abs(g.bench_only-g.actual_minutes).mean()),'mean_minute_shift':float(g.minute_shift.mean()),'net_total_absolute_error_change':float(g.error_change.sum()),'worsened':int((g.error_change>1e-8).sum()),'improved':int((g.error_change< -1e-8).sum()),'worsened_with_downward_shift':int(((g.error_change>1e-8)&(g.minute_shift<0)).sum()),'worsened_with_upward_shift':int(((g.error_change>1e-8)&(g.minute_shift>0)).sum())}
    states=pd.DataFrame(json.loads((source/'absence_states.json').read_text()));states.game_id=states.game_id.astype(str);states.package=states.package.astype(str);keys=allf[allf.primary][['package','game_id','team']].drop_duplicates();states=states.merge(keys,on=['package','game_id','team'],validate='many_to_one');unknown_states=states[states.state=='unknown'];details=[]
    for r in unknown_states.itertuples():
        candidates=[v for v in positions[r.name,r.team] if v[0]<r.date and v[1]<pd.Timestamp(r.capture) and v[2]['minutes'] is not None and v[2]['minutes']>0];reference=max(candidates,key=lambda v:(v[0],v[1]))[2]['id'] if candidates else None
        for gid,label in zip(r.last3_games,r.last3_states):
            game=games.get(str(gid))
            if game is None:
                reason='raw_game_missing';rawrows=[]
            else:reason,rawrows=classify_raw_gap(r.name,r.team,game['athletes'],reference)
            out_stamps=[stamp for stamp in prior_out.get((str(gid),r.team,r.name),[]) if game and game['opening'] is not None and pd.Timestamp(stamp)<game['opening'] and pd.Timestamp(stamp)<pd.Timestamp(r.capture)]
            details.append({'prior_pregame_out_snapshots':out_stamps,'package':r.package,'forecast_game_id':r.game_id,'team':r.team,'name':r.name,'prior_game_id':gid,'existing_label':label,'reference_id':reference,'reason':reason,'raw_rows':rawrows,'source_sha256':game['sha256'] if game else None})
    gaps=[d for d in details if d['existing_label']=='unknown'];summary={'live_enabled':False,'target_definition':'Snapshot Injury Status=Active, provider-defined core>=28, historical-core OUT on same team; provider tier is diagnostic only','mechanism_scope':'No additional vacancy transfer was selected; all changes here arise from tiered history weights and240-minute normalization','candidate_parity_max_error':parity,'all_core':metrics(core),'all_active_core':metrics(core[core.snapshot_active]),'active_core_injury':metrics(target),'active_core_no_detected_vacancy':metrics(outside),'non_active_status_core':metrics(core[~core.snapshot_active]),'all_active_core_by_position':{str(k):metrics(g) for k,g in core[core.snapshot_active].groupby('prior_position')},'active_core_injury_by_position':{str(k):metrics(g) for k,g in target.groupby('prior_position')},'active_core_by_trend':{str(k):metrics(g) for k,g in core[core.snapshot_active].groupby('recent_trend')},'active_core_injury_by_trend':{str(k):metrics(g) for k,g in target.groupby('recent_trend')},'unknown_core_out_cases':len(unknown_states),'unknown_prior_game_observations':len(gaps),'unknown_reasons':dict(Counter(d['reason'] for d in gaps)),'unknown_prior_games_with_saved_pregame_out_evidence':sum(bool(d['prior_pregame_out_snapshots']) for d in gaps),'verified_parsing_gap_count':sum(d['reason'] in ['verified_id_name_key_gap','source_positive_minutes','source_explicit_dnp'] for d in gaps),'limitations':['Active is an archived availability label, not medical confirmation','Position comes from latest strictly earlier saved boxscore; small groups are descriptive','Player-group MAE changes and allocator counterfactuals are not causal game-outcome effects','Absence from a source list cannot be backfilled as DNP or injury','No thresholds, forecasts or production logic were retuned;29 games remain development data']}
    player_rows=[]
    for (team,name),g in core[core.snapshot_active].groupby(['team','name']):player_rows.append({'team':team,'name':name,**metrics(g)})
    pd.DataFrame(player_rows).sort_values('net_total_absolute_error_change',ascending=False).to_csv(out/'active_core_player_ranking.csv',index=False)
    evidence=[{'game_id':gid,'date':games[gid]['date'],'source_sha256':games[gid]['sha256'],'athletes':games[gid]['athletes']} for gid in sorted({str(d['prior_game_id']) for d in details}) if gid in games]
    (out/'raw_boxscore_evidence.json').write_text(json.dumps(evidence,indent=2))
    target.sort_values('error_change',ascending=False).to_csv(out/'active_core_injury_residuals.csv',index=False);f.to_csv(out/'all_core_context_rows.csv',index=False);(out/'unknown_raw_audit.json').write_text(json.dumps(details,indent=2));(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':run(sys.argv[1])
