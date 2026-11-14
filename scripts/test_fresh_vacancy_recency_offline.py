"""Recover saved available rosters, then run explicit-absence chronological tests."""
import gzip,json,sys
from collections import Counter
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.expand_minutes_evidence_offline import player_key,team_key
from scripts.slice_independent_minutes_context_offline import previous_rows
from simmah_nba_absence_recency_offline import absence_state,tiered_team,transfer_proposal


def load_participation(pbp):
    calendar=[];presence={};excluded=[]
    for path in sorted(Path(pbp).glob('*/*.json.gz')):
        d=json.loads(gzip.decompress(path.read_bytes()));events=d['events'];period=max(e.get('period',{}).get('number',0) for e in events)
        clocks=[pd.Timestamp(e['wallclock']) for e in events if e.get('wallclock')]
        final=period>=4 and any(e.get('period',{}).get('number')==period and e.get('clock',{}).get('displayValue') in ['0:00','0.0','0.00'] for e in events)
        if not clocks or not final:excluded.append(str(d['event_id']));continue
        gid=str(d['event_id']);completed=max(clocks).isoformat()
        for t in d['boxscore']['players']:
            team=team_key(t['team']['abbreviation']);calendar.append({'team':team,'date':d['date'],'game_id':gid,'completed_at':completed})
            for group in t['statistics']:
                for p in group['athletes']:
                    key=player_key(p['athlete']['displayName'],team);stats=dict(zip(group['labels'],p.get('stats',[])));raw=stats.get('MIN');minutes=None
                    try:minutes=float(raw)
                    except (TypeError,ValueError):pass
                    state='played' if minutes is not None and minutes>0 else 'dnp' if p.get('didNotPlay') is True and (minutes in [None,0.]) else 'unknown'
                    pk=(gid,key[0],key[1])
                    if pk in presence and presence[pk]!=state:raise ValueError('Contradictory participation record')
                    presence[pk]=state
    return calendar,presence,excluded


def run(root):
    root=Path(root);out=root/'fresh-vacancy-recency';out.mkdir(exist_ok=True)
    old=pd.read_csv(root/'independent-minutes-benchmark/site_predictions.csv',dtype={'package':str,'game_id':str,'player_id':str});unknown=pd.read_csv(root/'independent-minutes-benchmark/unmatched_forecasts.csv',dtype={'package':str,'game_id':str})
    history=json.loads((root/'independent-minutes-benchmark/history_rows.json').read_text());metas=json.loads((root/'independent-minutes-context/team_context.json').read_text())
    transitions=json.loads((root/'recipient-checkpoint/earlier-recipient-results/transitions.json').read_text());calendar,presence,excluded=load_participation(root/'simmah-nba-clock/data/nba_pbp');completion={g['game_id']:pd.Timestamp(g['completed_at']) for g in calendar}
    fractions=[0.,.25,.5,1.];rows=[];states=[];teams=[];maximum_parity=0.
    for meta in metas:
        package,gid,team=meta['package'],str(meta['game_id']),meta['team'];g=old[(old.package==package)&(old.game_id==gid)&(old.team==team)];u=unknown[(unknown.package==package)&(unknown.game_id==gid)&(unknown.team==team)]
        if g.empty:raise ValueError('Missing scored team snapshot')
        day=str(g.date.iloc[0]);capture=pd.Timestamp(g.capture.iloc[0]);names=g.name.tolist()+u.name.tolist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate reconstructed roster')
        roster=[{'name':n,'team':team,'status':'Active'} for n in names]
        base,tiered,tiers=tiered_team(roster,history,day,capture);keys=[tuple(p['key']) for p in base];b=np.array([p['predicted_minutes'] for p in base]);saved=dict(zip(g.name,g['rolling']));saved.update(dict(zip(u.name,u['rolling'])))
        parity=max(abs(p['predicted_minutes']-saved[p['key'][0]]) for p in base);maximum_parity=max(maximum_parity,parity)
        if parity>1e-8:raise AssertionError('Recovered roster fails original baseline parity')
        route=np.zeros(len(base));state_counts=Counter();unsupported=[]
        for donor_name in meta['historical_core_out']:
            key=(donor_name,team);status=absence_state(key,calendar,presence,day,capture);state_counts[status['state']]+=1;record={'package':package,'game_id':gid,'team':team,'date':day,'capture':capture.isoformat(),'name':donor_name,**status};states.append(record)
            if status['state']!='fresh':continue
            prior=previous_rows(history,key,day,capture,True)
            if not prior:raise AssertionError('Historical core has no prior positive minutes')
            amount=float(np.mean([h['minutes'] for h in prior]));counts=Counter()
            for t in transitions:
                if t['date']>=day or t['team']!=team or len(t['out'])!=1 or len(t['in'])!=1:continue
                if str(t['game_id']) not in completion or completion[str(t['game_id'])]>=capture:continue
                if player_key(t['out'][0],team)==key:
                    recipient=player_key(t['in'][0],team)
                    if recipient in keys:counts[recipient]+=1
            chosen=sorted(counts,key=lambda k:(-counts[k],k))[:2]
            if not chosen:unsupported.append(donor_name);continue
            denom=sum(counts[k] for k in chosen)
            for recipient in chosen:route[keys.index(recipient)]+=amount*counts[recipient]/denom
        fresh_b=transfer_proposal(b,route);fresh_t=transfer_proposal(tiered,route)
        vectors={'baseline':b,'tiered':tiered,**{'fresh_baseline_'+str(a):b+a*(fresh_b-b) for a in fractions},**{'fresh_tiered_'+str(a):tiered+a*(fresh_t-tiered) for a in fractions}}
        for arm,v in vectors.items():
            if not np.isfinite(v).all() or np.any(v< -1e-8) or np.any(v>48+1e-8) or abs(v.sum()-240)>1e-6:raise AssertionError('Invalid independent rotation '+arm)
        context='fresh_present' if state_counts['fresh'] else 'ongoing_3plus' if state_counts['ongoing_3plus'] and not state_counts['unknown'] and not state_counts['two_missed_transition'] else 'unknown_or_transition' if state_counts else 'no_detected_core_vacancy'
        team_meta={'package':package,'game_id':gid,'team':team,'date':day,'capture':capture.isoformat(),'core_out_count':len(meta['historical_core_out']),'states':dict(state_counts),'context':context,'unsupported_fresh_recipients':unsupported,'supported_fresh_minutes':float(route.sum()),'available_count':len(base),'unscored_available_count':len(u),'baseline_total':float(b.sum()),'tiered_total':float(tiered.sum())};teams.append(team_meta)
        for r in g.itertuples():
            i=keys.index((r.name,team));row=r._asdict();row.update({'core_vacancy':bool(meta['historical_core_out']),'absence_context':context,'historical_tier':tiers[i],'provider_tier':'zero' if r.provider==0 else 'bench' if r.provider<18 else 'rotation' if r.provider<28 else 'core',**{a:float(v[i]) for a,v in vectors.items()}});rows.append(row)
    f=pd.DataFrame(rows);choice=f[['package','game_id','team','capture']].drop_duplicates().sort_values(['capture','package']).drop_duplicates(['game_id','team'],keep='last');f['primary']=f.set_index(['package','game_id','team']).index.isin(choice.set_index(['package','game_id','team']).index)
    dates=sorted(f.date.unique());folds=[];evals=[]
    for day in dates[1:]:
        train=f[(f.date<day)&f.primary];test=f[f.date==day].copy()
        if set(train.game_id)&set(test.game_id):raise AssertionError('Fold leakage')
        def loss(arm):return float(train.assign(error=(train[arm]-train.actual_minutes).abs()).groupby('game_id').error.mean().mean())
        alpha_b=min(fractions,key=lambda a:(loss('fresh_baseline_'+str(a)),a));alpha_t=min(fractions,key=lambda a:(loss('fresh_tiered_'+str(a)),a))
        test['cv_fresh_baseline']=test['fresh_baseline_'+str(alpha_b)];test['cv_tiered_fresh']=test['fresh_tiered_'+str(alpha_t)]
        candidates=['baseline','tiered']+['fresh_baseline_'+str(a) for a in fractions]+['fresh_tiered_'+str(a) for a in fractions];selected=min(candidates,key=lambda a:(loss(a),a));test['cv_selected']=test[selected]
        folds.append({'evaluation_date':day,'max_train_date':str(train.date.max()),'training_games':train.game_id.nunique(),'baseline_fresh_fraction':alpha_b,'tiered_fresh_fraction':alpha_t,'selected_family':selected});evals.append(test)
    ev=pd.concat(evals,ignore_index=True);arms=['provider','baseline','tiered','cv_fresh_baseline','cv_tiered_fresh','cv_selected']
    def metrics(g,cols):return {'n':len(g),'games':g.game_id.nunique(),**{a:{'mae':float((g[a]-g.actual_minutes).abs().mean()),'bias':float((g[a]-g.actual_minutes).mean()),'miss_over5':float(((g[a]-g.actual_minutes).abs()>5).mean())} for a in cols}}
    p=f[f.primary&f.original_audit_cohort];e=ev[ev.primary];audit=e[e.original_audit_cohort]
    result={'live_enabled':False,'recovered_team_snapshots':len(teams),'recovered_available_roster_rows':sum(t['available_count'] for t in teams),'unscored_available_rows':sum(t['unscored_available_count'] for t in teams),'baseline_parity_max_error':maximum_parity,'participation_games':len(set(g['game_id'] for g in calendar)),'excluded_calendar_games':excluded,'out_core_states':dict(Counter(s['state'] for s in states)),'folds':folds,'all37_vacancy_slices':{str(k):metrics(g,['provider','baseline','tiered']) for k,g in p.groupby('core_vacancy')},'all37_absence_slices':{str(k):metrics(g,['provider','baseline','tiered']) for k,g in p.groupby('absence_context')},'evaluation_all_common':metrics(e,arms),'evaluation_audited':metrics(audit,arms),'evaluation_injury':metrics(audit[audit.core_vacancy],arms),'evaluation_by_provider_tier':{str(k):metrics(g,arms) for k,g in audit.groupby('provider_tier')},'evaluation_by_absence':{str(k):metrics(g,arms) for k,g in audit.groupby('absence_context')},'evaluation_by_site':{str(k):metrics(g[g.original_audit_cohort],arms) for k,g in ev.groupby('platform')},'bootstrap':{},'status':'Retrospective development chronological verification. No promotion, no fresh external holdout claim.'}
    state_frame=pd.DataFrame(states);primary_keys=f[f.primary][['package','game_id','team']].drop_duplicates();primary_states=state_frame.merge(primary_keys,on=['package','game_id','team'],validate='many_to_one')
    result['primary_out_core_states']=primary_states.state.value_counts().to_dict();result['supported_fresh_team_snapshot_count']=sum(t['supported_fresh_minutes']>0 for t in teams);result['unsupported_fresh_donor_snapshot_count']=sum(len(t['unsupported_fresh_recipients']) for t in teams)
    (out/'participation_features.json').write_text(json.dumps({'calendar':calendar,'participation':[{'game_id':g,'name':n,'team':t,'state':v} for (g,n,t),v in presence.items()]}))
    for label,g in [('all',audit),('injury',audit[audit.core_vacancy])]:
        result['bootstrap'][label]={}
        for arm in ['tiered','cv_fresh_baseline','cv_tiered_fresh','cv_selected']:
            for control in ['baseline','provider']:
                delta=g.assign(d=(g[arm]-g.actual_minutes).abs()-(g[control]-g.actual_minutes).abs()).groupby('game_id').d.mean().to_numpy();rng=np.random.default_rng(1414);result['bootstrap'][label][arm+'_minus_'+control]={'game_weighted_MAE_delta':float(delta.mean()),'bootstrap95':np.quantile(delta[rng.integers(len(delta),size=(2000,len(delta)))].mean(1),[.025,.975]).tolist()}
    f.to_csv(out/'all_date_predictions.csv',index=False);ev.to_csv(out/'chronological_predictions.csv',index=False);(out/'team_records.json').write_text(json.dumps(teams,indent=2));(out/'absence_states.json').write_text(json.dumps(states,indent=2));(out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':run(sys.argv[1])
