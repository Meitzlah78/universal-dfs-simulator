"""Small predeclared gate family; chronological selection and guard-only diagnostics."""
import gzip,json,sys
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_independent_minutes_offline import forecast_team
from simmah_nba_role_change_gate_offline import gated_minutes,starter_transition
from scripts.expand_minutes_evidence_offline import player_key,team_key


def run(root):
    root=Path(root);out=root/'role-gate';out.mkdir(exist_ok=True)
    old=pd.read_csv(root/'independent-minutes-benchmark/site_predictions.csv',dtype={'package':str,'game_id':str,'player_id':str});unknown=pd.read_csv(root/'independent-minutes-benchmark/unmatched_forecasts.csv',dtype={'package':str,'game_id':str});history=json.loads((root/'independent-minutes-benchmark/history_rows.json').read_text());meta={(m['package'],str(m['game_id']),m['team']):m for m in json.loads((root/'independent-minutes-context/team_context.json').read_text())}
    roles=pd.read_csv(out/'snapshot_roles.csv',dtype={'package':str,'player_id':str});rolemap={}
    for r in roles.itertuples():rolemap[(r.package,r.player_id)]={'expected':bool(r.expected_starter) if pd.notna(r.expected_starter) else None,'capture':pd.Timestamp(r.captured_at)}
    position=pd.read_csv(root/'core-regression-diagnostics/all_core_context_rows.csv',dtype={'package':str,'game_id':str});posmap={(r.package,r.game_id,r.team,r.name):r.prior_position for r in position.itertuples()}
    calendar=[];starters={}
    for path in sorted((root/'simmah-nba-clock/data/nba_pbp').glob('*/*.json.gz')):
        d=json.loads(gzip.decompress(path.read_bytes()));events=d['events'];period=max(e.get('period',{}).get('number',0) for e in events);clocks=[pd.Timestamp(e['wallclock']) for e in events if e.get('wallclock')];gid=str(d['event_id'])
        if not clocks or period<4 or not any(e.get('period',{}).get('number')==period and e.get('clock',{}).get('displayValue') in ['0:00','0.0','0.00'] for e in events):continue
        for team in d['boxscore']['players']:
            tk=team_key(team['team']['abbreviation']);calendar.append((gid,tk,d['date'],max(clocks)))
            for g in team['statistics']:
                for p in g['athletes']:
                    key=player_key(p['athlete']['displayName'],tk);stats=dict(zip(g['labels'],p.get('stats',[])));m=None
                    try:m=float(stats.get('MIN'))
                    except (TypeError,ValueError):pass
                    starters[gid,key[0],key[1]]={'started':p.get('starter') if isinstance(p.get('starter'),bool) else None,'played':True if m is not None and m>0 else False if p.get('didNotPlay') is True else None}
    variants=[(mode,t) for mode in ['baseline5','fast3'] for t in [2.,3.,4.]];rows=[];budgets=[];max_parity=0.
    for (package,gid,team),g in old.groupby(['package','game_id','team']):
        u=unknown[(unknown.package==package)&(unknown.game_id==gid)&(unknown.team==team)];roster=[{'name':n,'team':team,'status':'Active'} for n in g.name.tolist()+u.name.tolist()];day=g.date.iloc[0];capture=pd.Timestamp(g.capture.iloc[0]);m=meta[(package,gid,team)]
        base=forecast_team(roster,history,day,capture);long=forecast_team(roster,history,day,capture,window=10,half_life=5.);fast=forecast_team(roster,history,day,capture,window=3,half_life=1.);names=[p['key'][0] for p in base];b=np.array([p['raw_minutes'] for p in base]);l=np.array([p['raw_minutes'] for p in long]);v=np.array([p['raw_minutes'] for p in fast]);baseline=np.array([p['predicted_minutes'] for p in base]);tiered,_=gated_minutes(b,l,v,threshold=1000.)
        arrays={mode+'_'+str(t):gated_minutes(b,l,v,t,mode)[0] for mode,t in variants};arrays['baseline']=baseline;arrays['tiered']=tiered
        for arm,values in arrays.items():
            if not np.all((values>=0)&(values<=48)) or not np.isclose(values.sum(),240):raise AssertionError('Incomplete rotation '+arm)
        previous=sorted([x for x in calendar if x[1]==team and x[2]<day and x[3]<capture],key=lambda x:(x[2],x[3],x[0]),reverse=True);last_game=previous[0][0] if previous else None
        budgets.append({'package':package,'game_id':gid,'team':team,'available_players':len(names),'unscored_players':len(u),'triggered_core_3min':int(((b>=28)&(b-l>3)).sum()),'max_budget_error':float(max(abs(x.sum()-240) for x in arrays.values()))})
        for r in g.itertuples():
            i=names.index(r.name);max_parity=max(max_parity,abs(baseline[i]-r.rolling));role=rolemap.get((package,r.player_id));expected=role['expected'] if role else None
            if role and role['capture']!=capture:raise AssertionError('Expected starter snapshot timestamp mismatch')
            prior=starters.get((last_game,r.name,team),{});change=starter_transition(expected,prior.get('started'),prior.get('played'))
            item=r._asdict();item.update({'core_vacancy':bool(m['available_core_out_proxy']),'back_to_back':bool(m['back_to_back']),'prior_position':posmap.get((package,gid,team,r.name),'Unknown'),'starter_change':change,'expected_starter':expected,'prior_started':prior.get('started'),'last_team_game':last_game,'recent_rise':float(b[i]-l[i]),'gate3_trigger':bool(b[i]>=28 and b[i]-l[i]>3),'snapshot_active':str(r.availability).upper()=='ACTIVE','provider_tier':'zero' if r.provider==0 else 'bench' if r.provider<18 else 'rotation' if r.provider<28 else 'core',**{arm:float(x[i]) for arm,x in arrays.items()}});rows.append(item)
    if max_parity>1e-8:raise AssertionError('Original baseline drift')
    f=pd.DataFrame(rows);choice=f[['package','game_id','team','capture']].drop_duplicates().sort_values(['capture','package']).drop_duplicates(['game_id','team'],keep='last');f['primary']=f.set_index(['package','game_id','team']).index.isin(choice.set_index(['package','game_id','team']).index)
    dates=sorted(f.date.unique());evals=[];folds=[];gatearms=[mode+'_'+str(t) for mode,t in variants]
    for day in dates[1:]:
        train=f[(f.date<day)&f.primary];test=f[f.date==day].copy()
        if set(train.game_id)&set(test.game_id):raise AssertionError('Game leakage')
        def loss(arm):return float(train.assign(e=(train[arm]-train.actual_minutes).abs()).groupby('game_id').e.mean().mean())
        selected=min(gatearms,key=lambda a:(loss(a),a));family=min(['baseline','tiered']+gatearms,key=lambda a:(loss(a),a));test['cv_gate']=test[selected];test['cv_safe_family']=test[family];test['fixed_gate3']=test['baseline5_3.0']
        folds.append({'date':day,'latest_training_date':str(train.date.max()),'training_games':train.game_id.nunique(),'selected_gate':selected,'selected_family':family});evals.append(test)
    ev=pd.concat(evals,ignore_index=True);arms=['provider','baseline','tiered','fixed_gate3','cv_gate','cv_safe_family']
    def metric(g):return {'n':len(g),'games':g.game_id.nunique(),**{a:{'mae':float(abs(g[a]-g.actual_minutes).mean()),'bias':float((g[a]-g.actual_minutes).mean()),'miss_over5':float((abs(g[a]-g.actual_minutes)>5).mean())} for a in arms}}
    p=ev[ev.primary&ev.original_audit_cohort];guards=p[p.snapshot_active&(p.provider_tier=='core')&(p.prior_position=='G')];bootstrap={}
    for arm in ['fixed_gate3','cv_gate','cv_safe_family']:
        bootstrap[arm]={}
        for control in ['baseline','tiered','provider']:
            delta=p.assign(d=abs(p[arm]-p.actual_minutes)-abs(p[control]-p.actual_minutes)).groupby('game_id').d.mean().to_numpy();rng=np.random.default_rng(1415);bootstrap[arm][control]={'game_weighted_MAE_delta':float(delta.mean()),'bootstrap95':np.quantile(delta[rng.integers(len(delta),size=(2000,len(delta)))].mean(1),[.025,.975]).tolist()}
    summary={'live_enabled':False,'baseline_parity_max_error':max_parity,'folds':folds,'evaluated_audited':metric(p),'injury_audited':metric(p[p.core_vacancy]),'by_provider_tier':{str(k):metric(g) for k,g in p.groupby('provider_tier')},'guard_core_active':metric(guards),'guards_by_back_to_back':{str(k):metric(g) for k,g in guards.groupby('back_to_back')},'guards_by_snapshot_starter_change':{str(k):metric(g) for k,g in guards.groupby('starter_change')},'guards_by_prior_growth':{str(k):metric(g) for k,g in guards.groupby(guards.recent_rise>3)},'bootstrap':bootstrap,'mechanics':{'team_snapshots':len(budgets),'available_forecasts':sum(b['available_players'] for b in budgets),'unknown_actuals_unscored':sum(b['unscored_players'] for b in budgets),'max_budget_error':max(b['max_budget_error'] for b in budgets)},'limitations':['Repeatedly inspected development set; chronological separation does not create pristine holdout','Gate uses historical raw minute means only; expected starter and rest fields are diagnostic strata, not predictors','Expected-starter changes are saved provider expectations versus previous-game actual starter flags, not confirmed current starters','Missing athlete records never mean bench/DNP; unknown starter histories remain unknown','No injury boosts, absence labels, simulator variance, fantasy points or live selection settings changed'],'status':'Offline development evaluation, not promoted'}
    f.to_csv(out/'all_date_gate_predictions.csv',index=False);ev.to_csv(out/'chronological_gate_predictions.csv',index=False);guards.to_csv(out/'guard_diagnostics.csv',index=False);(out/'team_budget_checks.json').write_text(json.dumps(budgets,indent=2));(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':run(sys.argv[1])
