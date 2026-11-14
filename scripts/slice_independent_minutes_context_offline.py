"""Pregame injury/context slices and frozen-family chronological ablations."""
import gzip,json,sys
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_independent_minutes_offline import forecast_team
from simmah_nba_minutes import allocate_minutes
from scripts.fit_coupled_minutes_offline import load_archive
from scripts.expand_minutes_evidence_offline import player_key,team_key

OUT={'OUT','O','IR','SUSPENDED','INACTIVE'}

def previous_rows(history,key,day,capture,positive=False):
    return sorted([h for h in history if tuple(h['key'])==key and h['date']<day and pd.Timestamp(h['completed_at'])<capture and (not positive or h['minutes']>0)],key=lambda h:(h['date'],h['completed_at'],h['game_id']))[-5:]

def context_features(own,b2b,spread,vacancy,recipient):
    own=np.asarray(own,float)
    return np.column_stack([np.ones(len(own)),own/48.,own/48.*b2b,own/48.*spread/10.,own/48.*vacancy/30.,np.asarray(recipient,float)/30.])

def ridge_fit(x,y,penalty=10.):
    x=np.asarray(x,float);y=np.asarray(y,float)
    if len(x)!=len(y) or not len(y) or not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('Finite earlier-date training rows required')
    return np.linalg.solve(x.T@x+penalty*np.eye(x.shape[1]),x.T@y)

def normalized_blends(own,provider):
    own=np.asarray(own,float);provider=np.asarray(provider,float)
    if own.shape!=provider.shape or not np.isfinite(own).all() or abs(own.sum()-240)>1e-6:raise ValueError('Complete own rotation required')
    supported=bool(np.isfinite(provider).all() and np.all(provider>=0) and np.all(provider<=48) and np.count_nonzero(provider)>4)
    return {weight:allocate_minutes((weight*own+(1-weight)*provider)[None,:])[0] if supported else np.full(len(own),np.nan) for weight in [0.,.25,.5,.75,1.]},supported

def run(root):
    root=Path(root);out=root/'independent-minutes-context';out.mkdir(exist_ok=True)
    history=json.loads((root/'independent-minutes-benchmark/history_rows.json').read_text());old=pd.read_csv(root/'independent-minutes-benchmark/site_predictions.csv',dtype={'package':str,'game_id':str,'player_id':str})
    transitions=json.loads((root/'earlier-recipient-results/transitions.json').read_text());cal=[];completed_by_game={}
    for path in sorted((root/'simmah-nba-clock/data/nba_pbp').glob('*/*.json.gz')):
        d=json.loads(gzip.decompress(path.read_bytes()));clocks=[pd.Timestamp(e['wallclock']) for e in d['events'] if e.get('wallclock')]
        last_period=max(e.get('period',{}).get('number',0) for e in d['events'])
        final_boundary=last_period>=4 and any(e.get('period',{}).get('number')==last_period and e.get('clock',{}).get('displayValue') in ['0:00','0.0','0.00'] for e in d['events'])
        if not clocks or not final_boundary:continue
        completed_by_game[str(d['event_id'])]=max(clocks)
        for t in d['boxscore']['players']:cal.append((team_key(t['team']['abbreviation']),d['date'],max(clocks)))
    rows=[];allteams={};team_records=[]
    for path in sorted((root/'minutes-expanded-evidence').glob('*.zip')):
        pool,c,markets,_=load_archive(path);package=str(c['id']);day=c['date'];obs=old[old.package==package]
        for team,group in pool.groupby('Team'):
            tk=team_key(team);g=obs[obs.team==tk]
            if g.empty:continue
            capture=pd.Timestamp(g.capture.iloc[0]);gid=g.game_id.iloc[0];roster=[{'name':p['Name'],'team':team,'status':p.get('Injury Status','unknown')} for _,p in group.iterrows()]
            base=forecast_team(roster,history,day,capture);fast=forecast_team(roster,history,day,capture,window=3,half_life=1.);last=forecast_team(roster,history,day,capture,window=1);uniform=forecast_team(roster,history,day,capture,window=5,half_life=1e12)
            active=[tuple(p['key']) for p in base];own=np.array([p['predicted_minutes'] for p in base]);names=[p['name'] for p in base]
            core_out=[];unknown_out=[]
            for p in roster:
                if str(p['status']).upper() not in OUT:continue
                key=player_key(p['name'],team);prior=previous_rows(history,key,day,capture,True)
                if not prior:unknown_out.append(p['name']);continue
                role=float(np.mean([h['minutes'] for h in prior]))
                if role>=28:core_out.append((key,role))
            vacancy=sum(m for _,m in core_out);route=np.zeros(len(active));unsupported=[]
            # Conditional recipients use only pregame earlier transitions. Never later same-game pairs.
            for donor,amount in core_out:
                counts=Counter()
                for t in transitions:
                    if t['date']>=day or t['team']!=tk or len(t['out'])!=1 or len(t['in'])!=1:continue
                    if str(t['game_id']) not in completed_by_game or completed_by_game[str(t['game_id'])]>=capture:continue
                    if player_key(t['out'][0],team)==donor:
                        key=player_key(t['in'][0],team)
                        if key in active:counts[key]+=1
                choices=sorted(counts,key=lambda k:(-counts[k],k))[:2]
                if not choices:unsupported.append(donor[0]);continue
                total=sum(counts[k] for k in choices)
                for key in choices:route[active.index(key)]+=amount*counts[key]/total
            # Zero-sum point-forecast proposal: move a training-tunable fraction of supported vacancy.
            proposed=own.copy();receivers=np.flatnonzero(route>0);donors=np.flatnonzero(route==0);amount=min(float(route.sum()),float(proposed[donors].sum()),float((48-proposed[receivers]).sum()))
            if amount and len(receivers) and len(donors):
                proposed[donors]-=amount*proposed[donors]/proposed[donors].sum();remaining=amount
                for _ in range(len(receivers)+1):
                    ids=receivers[proposed[receivers]<48-1e-12]
                    if not len(ids) or remaining<1e-10:break
                    share=np.minimum(48-proposed[ids],remaining*route[ids]/route[ids].sum());proposed[ids]+=share;remaining-=share.sum()
                if remaining>1e-8:raise AssertionError('Unallocated vacancy proposal')
            previous=[d for t,d,end in cal if t==tk and d<day and end<capture];gap=(date.fromisoformat(day)-date.fromisoformat(max(previous))).days if previous else None;b2b=float(gap==1)
            matching=[m for m in markets if tk in [team_key(t) for t in m['teams']]];points=matching[0].get('implied_points') if len(matching)==1 else None;spread=float(abs(points[0]-points[1])) if points is not None else 0.;spread_missing=points is None
            out_recency={}
            for donor,_ in core_out:
                prior_all=previous_rows(history,donor,day,capture)
                if prior_all and previous and prior_all[-1]['date']==max(previous):out_recency[donor[0]]='played_last_game' if prior_all[-1]['minutes']>0 else 'already_absent'
                else:out_recency[donor[0]]='unknown'
            vacancy_state='new_or_mixed' if 'played_last_game' in out_recency.values() else 'already_absent' if out_recency and set(out_recency.values())=={'already_absent'} else 'unknown_recency' if out_recency else 'no_detected_core_vacancy'
            x=context_features(own,b2b,spread,vacancy,route);vectors={'baseline':own,'fast3':np.array([p['predicted_minutes'] for p in fast]),'last1':np.array([p['predicted_minutes'] for p in last]),'uniform5':np.array([p['predicted_minutes'] for p in uniform]),**{'vacancy_'+str(a):own+a*(proposed-own) for a in [0.,.25,.5,1.]}}
            provider_map={player_key(p['Name'],team):pd.to_numeric(pd.Series([p.get('Projected Minutes')]),errors='coerce').iloc[0] for _,p in group.iterrows()}
            provider_active=np.array([provider_map[k] for k in active],float)
            normalized,normalized_supported=normalized_blends(own,provider_active)
            for weight,v in normalized.items():vectors['normalized_blend_'+str(weight)]=v
            for arm,v in vectors.items():
                if arm.startswith('normalized_blend_') and not normalized_supported:continue
                if not np.isfinite(v).all() or np.any(v< -1e-8) or np.any(v>48+1e-8) or abs(v.sum()-240)>1e-6:raise AssertionError('Invalid independent arm budget: '+arm)
            meta={'package':package,'game_id':gid,'team':tk,'day':day,'capture':capture.isoformat(),'historical_core_out':[k[0] for k,_ in core_out],'vacancy_minutes':vacancy,'normalized_blend_supported':normalized_supported,'out_with_unknown_positive_history':unknown_out,'unsupported_vacancy_donors':unsupported,'rest_days':gap,'back_to_back':bool(b2b),'spread':spread,'spread_missing':spread_missing,'available_core_out_proxy':bool(core_out),'core_out_recency':out_recency,'vacancy_state':vacancy_state,'unresolved_QD':any(str(p['status']).upper() in ['QUESTIONABLE','DOUBTFUL','Q','D'] for p in roster)}
            key=(package,gid,tk);allteams[key]={'vectors':vectors,'features':x,'names':active,'meta':meta};team_records.append(meta)
            for r in g.itertuples():
                keyp=(r.name,tk);i=active.index(keyp);item=r._asdict();item.update(meta);item.update({arm:float(v[i]) for arm,v in vectors.items()});item['independent_tier']='bench' if own[i]<18 else 'rotation' if own[i]<28 else 'core';item['provider_tier']='zero' if r.provider==0 else 'bench' if r.provider<18 else 'rotation' if r.provider<28 else 'core';item['features']=x[i].tolist();rows.append(item)
    f=pd.DataFrame(rows);choice=f[['package','game_id','team','capture']].drop_duplicates().sort_values(['capture','package']).drop_duplicates(['game_id','team'],keep='last')[['package','game_id','team']];f['primary']=f.set_index(['package','game_id','team']).index.isin(choice.set_index(['package','game_id','team']).index)
    dates=sorted(f.date.unique());folds=[];evaluated=[]
    for day in dates[1:]:
        train=f[(f.date<day)&f.primary].copy();test=f[f.date==day].copy()
        if set(train.game_id)&set(test.game_id):raise AssertionError('Temporal game overlap')
        # Candidate selection uses earlier physical-game-average MAE, including provider-zero rows.
        def loss(arm):return float(train.assign(e=(train[arm]-train.actual_minutes).abs()).groupby('game_id').e.mean().mean())
        recency=min(['baseline','fast3','last1','uniform5'],key=lambda arm:(loss(arm),arm));vacancy=min(['vacancy_0.0','vacancy_0.25','vacancy_0.5','vacancy_1.0'],key=lambda arm:(loss(arm),arm));beta=ridge_fit(np.stack(train.features),train.actual_minutes-train.baseline)
        test['cv_recency']=test[recency];test['cv_vacancy']=test[vacancy];context_predictions={}
        for key,t in allteams.items():
            if t['meta']['day']!=day:continue
            proposal=np.clip(t['vectors']['baseline']+t['features']@beta,0.,48.);pred=allocate_minutes(proposal[None,:])[0]
            for k,v in zip(t['names'],pred):context_predictions[(key[0],key[1],key[2],k[0])]=v
        test['cv_context']=[context_predictions[(r.package,r.game_id,r.team,r.name)] for r in test.itertuples()]
        train_blends={a:float(train.assign(e=(a*train.baseline+(1-a)*train.provider-train.actual_minutes).abs()).groupby('game_id').e.mean().mean()) for a in [0.,.25,.5,.75,1.]};weight=min(train_blends,key=lambda a:(train_blends[a],a));test['cv_blend']=weight*test.baseline+(1-weight)*test.provider
        normalized_weight=min([0.,.25,.5,.75,1.],key=lambda a:(loss('normalized_blend_'+str(a)),a)) if train.normalized_blend_supported.any() else 0.;test['cv_normalized_blend']=test['normalized_blend_'+str(normalized_weight)];test['provider_normalized']=test['normalized_blend_0.0']
        folds.append({'test_date':day,'max_train_date':str(train.date.max()),'training_games':train.game_id.nunique(),'selected_recency':recency,'selected_vacancy':vacancy,'context_beta':beta.tolist(),'blend_independent_weight':weight,'normalized_blend_independent_weight':normalized_weight});evaluated.append(test)
    ev=pd.concat(evaluated,ignore_index=True);arms=['provider','baseline','fast3','last1','uniform5','cv_recency','cv_vacancy','cv_context','cv_blend','provider_normalized','cv_normalized_blend']
    def metric(g,columns):return {'n':len(g),'games':g.game_id.nunique(),'n_by_arm':{a:int(g[a].notna().sum()) for a in columns},**{a:float((g[a]-g.actual_minutes).abs().mean()) for a in columns}}
    full={'feature_definitions':{'injury_affected':'At least one currently OUT player has mean>=28 in last5 earlier positive-minute observations; no provider role feature','no_detected_vacancy':'Not established full strength: no detected historical-core OUT; unknown histories/Q/D remain explicit','recency_baseline':'Already last5 with exponential half-life3; not a uniform/full-season baseline','spread':'Absolute difference in archived implied team points; missing kept flagged, numerical zero only in regression feature','rest':'Earlier completed team game calendar includes OT; same-day games excluded'},'slices_full_primary_audit':{},'chronological_evaluation':{},'folds':folds,'missing_actual_handling':'Same scored cohort as prior benchmark;259 unavailable actual records remain unscored, no reclassification','status':'Development chronological comparison, no untouched holdout or live promotion'}
    p=f[f.primary&f.original_audit_cohort]
    for k,g in p.groupby('available_core_out_proxy'):full['slices_full_primary_audit']['injury' if k else 'no_detected_core_vacancy']=metric(g,['provider','baseline'])
    full['slices_full_primary_audit']['by_vacancy_recency']={k:metric(g,['provider','baseline']) for k,g in p.groupby('vacancy_state')}
    full['slices_full_primary_audit']['by_provider_tier']={k:metric(g,['provider','baseline']) for k,g in p.groupby('provider_tier')}
    e=ev[ev.primary];full['chronological_evaluation']['all_common']=metric(e,arms);full['chronological_evaluation']['original_audit']=metric(e[e.original_audit_cohort],arms);full['chronological_evaluation']['injury_slices']={str(k):metric(g,arms) for k,g in e[e.original_audit_cohort].groupby('available_core_out_proxy')};full['chronological_evaluation']['by_site_original_audit']={site:metric(g[g.original_audit_cohort],arms) for site,g in ev.groupby('platform')};full['chronological_evaluation']['by_provider_tier']={k:metric(g,arms) for k,g in e[e.original_audit_cohort].groupby('provider_tier')}
    full['chronological_evaluation']['normalized_complete_original_audit']=metric(e[e.original_audit_cohort&e.normalized_blend_supported],arms)
    bootstrap={}
    for arm in ['baseline','cv_recency','cv_vacancy','cv_context','cv_blend','provider_normalized','cv_normalized_blend']:
        delta=e.assign(d=(e[arm]-e.actual_minutes).abs()-(e.provider-e.actual_minutes).abs()).groupby('game_id').d.mean().dropna().to_numpy();rng=np.random.default_rng(1411);bootstrap[arm]={'game_weighted_MAE_delta':float(delta.mean()),'bootstrap95':np.quantile(delta[rng.integers(len(delta),size=(2000,len(delta)))].mean(1),[.025,.975]).tolist()}
    delta=e.assign(d=(e.cv_normalized_blend-e.actual_minutes).abs()-(e.provider_normalized-e.actual_minutes).abs()).groupby('game_id').d.mean().dropna().to_numpy();rng=np.random.default_rng(1411);bootstrap['normalized_blend_vs_normalized_provider']={'game_weighted_MAE_delta':float(delta.mean()),'bootstrap95':np.quantile(delta[rng.integers(len(delta),size=(2000,len(delta)))].mean(1),[.025,.975]).tolist()}
    full['conditional_game_bootstrap']=bootstrap;full['team_context_counts']={'snapshots':len(team_records),'historical_core_vacancy':sum(t['available_core_out_proxy'] for t in team_records),'unknown_out_history':sum(bool(t['out_with_unknown_positive_history']) for t in team_records),'unresolved_QD':sum(t['unresolved_QD'] for t in team_records),'spread_missing':sum(t['spread_missing'] for t in team_records),'back_to_back':sum(t['back_to_back'] for t in team_records),'rest_unknown':sum(t['rest_days'] is None for t in team_records),'normalized_blend_unsupported':sum(not t['normalized_blend_supported'] for t in team_records)}
    f.drop(columns=['features']).to_csv(out/'context_slices.csv',index=False);ev.drop(columns=['features']).to_csv(out/'chronological_predictions.csv',index=False);(out/'team_context.json').write_text(json.dumps(team_records,indent=2));(out/'summary.json').write_text(json.dumps(full,indent=2));print(json.dumps(full,indent=2))
if __name__=='__main__':run(sys.argv[1])
