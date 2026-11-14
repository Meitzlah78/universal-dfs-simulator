"""Frozen history-only baseline vs saved provider inputs; no production changes."""
import gzip,hashlib,json,sys
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_independent_minutes_offline import forecast_team
from scripts.fit_coupled_minutes_offline import load_archive
from scripts.expand_minutes_evidence_offline import player_key,team_key

def history_rows(root):
    rows=[];excluded=[]
    for path in sorted((root/'simmah-nba-clock/data/nba_pbp').glob('*/*.json.gz')):
        d=json.loads(gzip.decompress(path.read_bytes()));events=d['events'];gid=str(d['event_id']);period=max(e.get('period',{}).get('number',0) for e in events)
        if period!=4 or not any(e.get('period',{}).get('number')==4 and e.get('clock',{}).get('displayValue') in ['0:00','0.0','0.00'] for e in events):
            excluded.append({'game_id':gid,'reason':'OT or unverified final regulation boundary'});continue
        clocks=[pd.Timestamp(e['wallclock']) for e in events if e.get('wallclock')]
        if not clocks:excluded.append({'game_id':gid,'reason':'no completed timestamp'});continue
        completed=max(clocks).isoformat()
        for t in d['boxscore']['players']:
            for g in t['statistics']:
                for p in g['athletes']:
                    s=dict(zip(g['labels'],p.get('stats',[])));key=player_key(p['athlete']['displayName'],t['team']['abbreviation'])
                    if s.get('MIN') not in [None,'','--']:
                        try:m=float(s['MIN'])
                        except ValueError:continue
                    elif p.get('didNotPlay') is True:m=0.
                    else:continue
                    if not 0<=m<=48:continue
                    rows.append({'key':key,'minutes':m,'date':d['date'],'completed_at':completed,'game_id':gid})
    return rows,excluded

def metrics(g):
    result={'n':len(g),'games':g.game_id.nunique()}
    for arm in ['provider','rolling','frozen']:
        delta=g[arm]-g.actual_minutes;result[arm]={'mae':float(delta.abs().mean()),'rmse':float(np.sqrt((delta**2).mean())),'bias_predicted_minus_actual':float(delta.mean()),'miss_over5':float((delta.abs()>5).mean())}
    return result

def run(root):
    root=Path(root);out=root/'independent-minutes-benchmark';out.mkdir(exist_ok=True)
    history,excluded=history_rows(root);(out/'history_rows.json').write_text(json.dumps(history));f=pd.read_csv(root/'minutes-script-results/all_forecasts_context.csv',dtype={'package':str,'game_id':str,'player_id':str});c=pd.read_csv(root/'minutes-role-results/actual_context.csv',dtype={'game_id':str})
    auditkeys=set(zip(f.package,f.player_id));predictions=[];teams=[];errors=[];unmatched=[]
    for path in sorted((root/'minutes-expanded-evidence').glob('*.zip')):
        pool,contest,_,_=load_archive(path);package=str(contest['id']);date=contest['date'];obs=f[f.package==package]
        for team,allrows in pool.groupby('Team'):
            normalized=team_key(team);g=obs[obs.team_key==normalized]
            if g.empty:continue
            if g.game_id.nunique()!=1:raise ValueError('Ambiguous team game')
            gid=str(g.game_id.iloc[0]);capture=pd.to_datetime(g.captured_at,utc=True,format='mixed').max()
            opening=pd.to_datetime(g.observed_opening_utc,utc=True,format='mixed').min()
            if capture>=opening:raise ValueError('Not a pregame snapshot')
            if (g.overtimes>0).any():continue
            # Estimator sees only these three fields, never minutes/points/roles/salary.
            roster=[{'name':r['Name'],'team':team,'status':r.get('Injury Status','unknown')} for _,r in allrows.iterrows()]
            try:
                rolling=forecast_team(roster,history,date,capture);frozen=forecast_team(roster,history,date,capture,history_ceiling='2026-11-06')
            except ValueError as e:errors.append({'package':package,'team':team,'reason':str(e)});continue
            a={tuple(r['key']):r for r in rolling};b={tuple(r['key']):r for r in frozen}
            actual=c[(c.game_id==gid)&(c.team_key==normalized)];truth={r.name_key:r.actual_minutes for r in actual.itertuples()}
            for _,p in allrows.iterrows():
                key=player_key(p['Name'],team)
                if key not in a:continue
                provider=pd.to_numeric(pd.Series([p.get('Projected Minutes')]),errors='coerce').iloc[0]
                if not np.isfinite(provider) or not 0<=provider<=48 or key[0] not in truth:
                    unmatched.append({'package':package,'game_id':gid,'team':normalized,'name':key[0],'rolling':a[key]['predicted_minutes'],'frozen':b[key]['predicted_minutes'],'cold_start':a[key]['cold_start'],'history_n':a[key]['history_n'],'reason':'missing explicit actual' if key[0] not in truth else 'invalid provider minutes'})
                    continue
                predictions.append({'package':package,'date':date,'platform':contest['platform'],'game_id':gid,'team':normalized,'name':key[0],'player_id':str(p['Player ID']),'capture':capture.isoformat(),'provider':float(provider),'rolling':a[key]['predicted_minutes'],'frozen':b[key]['predicted_minutes'],'actual_minutes':float(truth[key[0]]),'raw_minutes':a[key]['raw_minutes'],'history_n':a[key]['history_n'],'cold_start':a[key]['cold_start'],'last_history_date':a[key]['last_history_date'],'provider_positive':provider>0,'original_audit_cohort':(package,str(p['Player ID'])) in auditkeys,'provider_source':p.get('Minutes Source','unknown'),'availability':p.get('Injury Status','unknown')})
            provider_vals=pd.to_numeric(allrows['Projected Minutes'],errors='coerce')
            active=~allrows['Injury Status'].astype(str).str.upper().isin(['OUT','O','IR','SUSPENDED','INACTIVE'])
            teams.append({'package':package,'game_id':gid,'team':normalized,'capture':capture.isoformat(),'rolling_total':sum(x['predicted_minutes'] for x in rolling),'frozen_total':sum(x['predicted_minutes'] for x in frozen),'provider_available_total':float(provider_vals[active].sum()),'available_roster_size':len(a),'all_available_cold_starts':sum(r['cold_start'] for r in rolling),'matched_actual_players':len(set(n[0] for n in a)&set(truth)),'actual_players_unrepresented_by_available_roster':len([n for n,m in truth.items() if m>0 and n not in set(k[0] for k in a)])})
    p=pd.DataFrame(predictions);t=pd.DataFrame(teams);choice=t.sort_values(['capture','package']).drop_duplicates(['game_id','team'],keep='last')[['package','game_id','team']]
    primary=p.merge(choice,on=['package','game_id','team'],validate='many_to_one');
    scored=p.groupby(['package','game_id','team'])['rolling'].sum().reset_index(name='scored_own_minutes');coverage=t.merge(scored,on=['package','game_id','team'],validate='one_to_one');coverage['unscored_own_minutes']=coverage.rolling_total-coverage.scored_own_minutes;coverage.to_csv(out/'roster_scoring_coverage.csv',index=False);
    pd.DataFrame(unmatched).to_csv(out/'unmatched_forecasts.csv',index=False);p.to_csv(out/'site_predictions.csv',index=False);primary.to_csv(out/'primary_predictions.csv',index=False);t.to_csv(out/'team_budgets.csv',index=False)
    result={'live_enabled':False,'feature_policy':'Names, teams and archived injury availability only; no provider minutes, FP projections, salary, starter flags or derived tiers enter prediction','rows':len(p),'primary_rows':len(primary),'primary_games':primary.game_id.nunique(),'builds':p.package.nunique(),'historical_game_rows':len(history),'historical_games':len(set(h['game_id'] for h in history)),'excluded_history_games':excluded,'errors':errors,'unmatched_available_forecasts':len(unmatched),'unmatched_reasons':pd.Series([r['reason'] for r in unmatched]).value_counts().to_dict(),'all_available_cold_starts':int(t.all_available_cold_starts.sum()),'unscored_prediction_mass_mean_per_team_snapshot':float(coverage.unscored_own_minutes.mean()),'actual_playing_players_outside_saved_available_roster_team_snapshots':int((t.actual_players_unrepresented_by_available_roster>0).sum()),'all_common_available_rows':metrics(primary),'original_audit_cohort':metrics(primary[primary.original_audit_cohort]),'cold_start_fraction':float(primary.cold_start.mean()),'cold_start':metrics(primary[primary.cold_start]) if primary.cold_start.any() else None,'history_supported':metrics(primary[~primary.cold_start]),'site_original_audit':{site:metrics(g[g.original_audit_cohort]) for site,g in p.groupby('platform')},'provider_sources':p.provider_source.fillna('missing').value_counts().to_dict(),'point_in_time':'Rolling inputs strictly earlier game dates and completed_at < capture; frozen sensitivity also excludes all history on/afterNov6','status':'Retrospective development benchmark, not untouched external holdout; point forecasts only, no interval or fantasy accuracy claim'}
    errors_by_game=primary.assign(delta=(primary['rolling']-primary.actual_minutes).abs()-(primary.provider-primary.actual_minutes).abs()).groupby('game_id').delta.mean().to_numpy();rng=np.random.default_rng(1411)
    result['rolling_minus_provider_mae_game_weighted']={'delta':float(errors_by_game.mean()),'bootstrap95':np.quantile(errors_by_game[rng.integers(len(errors_by_game),size=(2000,len(errors_by_game)))].mean(1),[.025,.975]).tolist()}
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='excluded_history_games'},indent=2))
if __name__=='__main__':run(sys.argv[1])
