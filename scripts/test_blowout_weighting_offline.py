"""Freeze existing gate and roles; vary historical-margin weights only."""
import gzip,json,sys
from pathlib import Path
from collections import defaultdict,Counter
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_blowout_weight_offline import margin_profile,discounted_recent_mean,SCHEMES
from simmah_nba_independent_minutes_offline import forecast_team
from simmah_nba_minutes import allocate_minutes


def run(root):
    root=Path(root);out=root/'blowout-weight-test';out.mkdir(exist_ok=True)
    history=json.loads((root/'independent-minutes-benchmark/history_rows.json').read_text());old=pd.read_csv(root/'role-gate/all_date_gate_predictions.csv',dtype={'package':str,'game_id':str});unknown=pd.read_csv(root/'independent-minutes-benchmark/unmatched_forecasts.csv',dtype={'package':str,'game_id':str});profiles={};bykey=defaultdict(list)
    for h in history:bykey[tuple(h['key'])].append(h)
    for path in sorted((root/'simmah-nba-clock/data/nba_pbp').glob('*/*.json.gz')):
        d=json.loads(gzip.decompress(path.read_bytes()));clocks=[pd.Timestamp(e['wallclock']) for e in d['events'] if e.get('wallclock')]
        if not clocks:continue
        profiles[str(d['event_id'])]={**margin_profile(d['events'],d['home_score'],d['away_score']),'completed_at':max(clocks).isoformat(),'date':d['date']}
    rows=[];teams=[];maximum_parity=0.
    for (package,gid,team),g in old.groupby(['package','game_id','team']):
        u=unknown[(unknown.package==package)&(unknown.game_id==gid)&(unknown.team==team)];roster=[{'name':n,'team':team,'status':'Active'} for n in g.name.tolist()+u.name.tolist()];day=g.date.iloc[0];capture=g.capture.iloc[0]
        base=forecast_team(roster,history,day,capture);long=forecast_team(roster,history,day,capture,window=10,half_life=5.);names=[p['key'][0] for p in base];braw=np.array([p['raw_minutes'] for p in base]);lraw=np.array([p['raw_minutes'] for p in long]);core=braw>=28;bench=braw<18;rise=core&((braw-lraw)>2.)
        windows=[(5,3.) if rise[i] or not(core[i] or bench[i]) else (10,5.) if core[i] else (3,1.) for i in range(len(base))];arrays={};notes={}
        for scheme in SCHEMES:
            estimates=[];n_discounted=n_missing=0
            for i,p in enumerate(base):
                window,half=windows[i];estimate,note=discounted_recent_mean(bykey[tuple(p['key'])],day,capture,window,half,profiles,scheme,p['raw_minutes']);estimates.append(estimate);n_discounted+=note['discounted'];n_missing+=note['missing_profile']
            arrays[scheme]=allocate_minutes(np.asarray(estimates)[None,:])[0];notes[scheme]={'selected_window_discounted_observations':n_discounted,'selected_window_missing_margin_observations':n_missing}
            if not np.all((arrays[scheme]>=0)&(arrays[scheme]<=48)) or abs(arrays[scheme].sum()-240)>1e-6:raise AssertionError('Invalid rotation')
        teams.append({'package':package,'game_id':gid,'team':team,'available':len(base),'unscored':len(u),'notes':notes,'max_budget_error':float(max(abs(v.sum()-240) for v in arrays.values()))})
        for r in g.to_dict('records'):
            i=names.index(r['name']);maximum_parity=max(maximum_parity,abs(arrays['none'][i]-r['baseline5_2.0']));rows.append({**r,**{s:float(a[i]) for s,a in arrays.items()}})
    if maximum_parity>1e-8:raise AssertionError('Control gate parity failure')
    f=pd.DataFrame(rows);dates=sorted(f.date.unique());evals=[];folds=[]
    for day in dates[1:]:
        train=f[(f.date<day)&f.primary];test=f[f.date==day].copy()
        if set(train.game_id)&set(test.game_id):raise AssertionError('Temporal leakage')
        def loss(s):return float(train.assign(e=abs(train[s]-train.actual_minutes)).groupby('game_id').e.mean().mean())
        choices={}
        for label,candidates in [('cv_final',['none']+[s for s in SCHEMES if s.startswith('final_')]),('cv_q4',['none']+[s for s in SCHEMES if s.startswith('q4_')]),('cv_all',SCHEMES)]:
            selected=min(candidates,key=lambda s:(loss(s),SCHEMES.index(s)));choices[label]=selected;test[label]=test[selected]
        folds.append({'date':day,'latest_train_date':str(train.date.max()),'train_games':train.game_id.nunique(),'choices':choices});evals.append(test)
    ev=pd.concat(evals,ignore_index=True);p=ev[ev.primary&ev.original_audit_cohort];arms=['provider','none']+SCHEMES[1:]+['cv_final','cv_q4','cv_all']
    def metrics(g):return {'n':len(g),'games':g.game_id.nunique(),**{a:{'mae':float(abs(g[a]-g.actual_minutes).mean()),'bias':float((g[a]-g.actual_minutes).mean()),'miss_over5':float((abs(g[a]-g.actual_minutes)>5).mean())} for a in arms}}
    used=set(h['game_id'] for h in history);available=[profiles[g] for g in used if g in profiles];summary={'live_enabled':False,'gate_control_parity_max_error':maximum_parity,'history_margin_coverage':{'historical_games':len(used),'final_profiles':sum(x.get('final_abs_margin') is not None for x in available),'q4_profiles':sum(x.get('q4_last6_mean_abs_margin') is not None for x in available),'all_quarter_end_margins':sum(set(x['quarter_end_home_minus_away'])=={'1','2','3','4'} for x in available),'q4_issues':dict(Counter(x['q4_issue'] for x in available if x['q4_issue']))},'folds':folds,'evaluated_audited':metrics(p),'by_provider_tier':{str(k):metrics(g) for k,g in p.groupby('provider_tier')},'injury_audited':metrics(p[p.core_vacancy]),'rising_core':metrics(p[(p.provider_tier=='core')&(p.recent_rise>3)]),'stable_expected_starter_core':metrics(p[(p.provider_tier=='core')&(p.starter_change=='stable_expected_starter')]),'guard_active_core':metrics(p[(p.provider_tier=='core')&p.snapshot_active&(p.prior_position=='G')]),'bootstrap':{},'mechanics':{'team_snapshots':len(teams),'available_forecasts':sum(t['available'] for t in teams),'unscored_forecasts':sum(t['unscored'] for t in teams),'max_budget_error':max(t['max_budget_error'] for t in teams)},'status':'Chronological repeated development comparison, no promotion; starter definition/gate triggering unchanged'}
    for arm in ['cv_final','cv_q4','cv_all']:
        summary['bootstrap'][arm]={}
        for label,g in [('all',p),('core',p[p.provider_tier=='core'])]:
            delta=g.assign(d=abs(g[arm]-g.actual_minutes)-abs(g['none']-g.actual_minutes)).groupby('game_id').d.mean().to_numpy();rng=np.random.default_rng(1416);summary['bootstrap'][arm][label]={'game_weighted_MAE_delta':float(delta.mean()),'bootstrap95':np.quantile(delta[rng.integers(len(delta),size=(2000,len(delta)))].mean(1),[.025,.975]).tolist()}
    f.to_csv(out/'all_date_predictions.csv',index=False);ev.to_csv(out/'chronological_predictions.csv',index=False);(out/'historical_margin_profiles.json').write_text(json.dumps(profiles,indent=2));(out/'team_checks.json').write_text(json.dumps(teams,indent=2));(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':run(sys.argv[1])
