"""Automatic component learning from already-archived completed NFL plays.

Three chronological blocks: fit, choose, then independently validate. A supported
component can pass while missing data blocks a different component. These are
conditional event scores, not evidence of calibrated whole-game fantasy outcomes.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm,gamma,t
from simmah_nfl_learning import (DEFAULTS,BOUNDS,ROOT,load_archives,event_samples,regulation,
    atomic_json,digest,engine_digest,model_for_date)

BINARY=('pass_rate','sack_rate','interception_rate','completion_rate','fumble_loss_rate',
        'extra_point_rate','two_point_rate','two_point_pass_share','two_point_pass_success',
        'two_point_run_success','defensive_return_td_rate')
SUPPORTED=(*BINARY,'rushing_distribution','receiving_shape','field_goal_logit_offset')
QUANTILES=(np.arange(128)+.5)/128
CRPS_WEIGHTS=(2*np.arange(128)-127)/128**2


def block_samples(frame):
    observations={name:[] for name in SUPPORTED}
    for gid,rows in frame.groupby('game_id',sort=True):
        values,_=event_samples(rows)
        for name in BINARY:
            if name in values and len(values[name]):observations[name].append((str(gid),values[name]))
        plays=regulation(rows)
        plays=plays.loc[plays.play_type.isin(['pass','run'])&plays.two_point_attempt.eq(0)&plays.extra_point_attempt.eq(0)]
        rushing=plays.loc[plays.play_type.eq('run')]
        receiving=plays.loc[plays.play_type.eq('pass')&plays.sack.eq(0)&plays.interception.eq(0)&plays.complete_pass.eq(1)]
        if {'field_goal_result','kick_distance','field_goal_attempt'}<=set(plays):
            kicks=regulation(rows).loc[lambda x:x.field_goal_attempt.eq(1)].copy()
            kicks['result']=kicks.field_goal_result.map({'made':1.,'missed':0.,'blocked':0.})
            kicks['distance']=pd.to_numeric(kicks.kick_distance,errors='coerce')
            kicks=kicks.loc[kicks.result.notna()&kicks.distance.notna()]
            if len(kicks):observations['field_goal_logit_offset'].append((str(gid),kicks[['result','distance']]))
        for name,subset,pid in [('rushing_distribution',rushing,'rusher_player_id'),('receiving_shape',receiving,'receiver_player_id')]:
            if pid not in subset:continue
            subset=subset.loc[subset[pid].notna()]
            if len(subset):
                observations[name].append((str(gid),subset[[pid,'yards_gained']].rename(columns={pid:'player_id'}).copy()))
    return observations


def means_from_training(observations,name):
    fallback=DEFAULTS['rushing_yards' if name=='rushing_distribution' else 'receiving_yards']
    frames=[values for _,values in observations[name]]
    if not frames:return {}
    frame=pd.concat(frames);group=frame.groupby('player_id').yards_gained.agg(['sum','count'])
    # Freeze the same history-conditioned mean for both versions; only spread is
    # tested. These are validation predictors, never replacements for CSV means.
    prior=30. if name=='rushing_distribution' else 10.
    lower,upper=BOUNDS['rushing_yards' if name=='rushing_distribution' else 'receiving_yards']
    return ((group['sum']+prior*fallback)/(group['count']+prior)).clip(lower,upper).to_dict()


def losses(observations,name,value,means,tail=False):
    result={}
    for gid,actual in observations[name]:
        if name=='field_goal_logit_offset':
            distance=actual.distance.to_numpy(float);y=actual.result.to_numpy(float)
            p=np.clip(.97-.005*np.maximum(distance-30,0)-.009*np.maximum(distance-45,0),.35,.98)
            logits=np.log(p/(1-p))+value
            result[gid]=float(np.mean(np.logaddexp(0,logits)-y*logits))
        elif name in BINARY:
            p=float(np.clip(value,1e-6,1-1e-6))
            result[gid]=float(-np.mean(actual*np.log(p)+(1-actual)*np.log1p(-p)))
        else:
            fallback=DEFAULTS['rushing_yards' if name=='rushing_distribution' else 'receiving_yards']
            mu=actual.player_id.map(means).fillna(fallback).to_numpy(float)
            y=pd.to_numeric(actual.yards_gained,errors='coerce').to_numpy(float)
            if not np.isfinite(y).all():raise ValueError('Missing event yardage')
            if name=='rushing_distribution':
                sd,df=value['sd'],value['df']
                z=norm.ppf(QUANTILES) if df==0 else t.ppf(QUANTILES,df)*np.sqrt((df-2)/df)
                draws=np.clip(mu[:,None]+sd*z[None,:],-5,65)
            else:draws=np.clip(gamma.ppf(QUANTILES,value)[None,:]*mu[:,None]/value,0,85)
            # CRPS evaluates observations outside a model's support as well;
            # negative completed gains are retained, never clipped to zero.
            if tail:
                thresholds=[10.,20.] if name=='rushing_distribution' else [20.,40.]
                terms=[]
                for cut in thresholds:
                    if name=='rushing_distribution':
                        standardized=(cut-mu)/sd
                        probability=norm.sf(standardized) if df==0 else t.sf(standardized/np.sqrt((df-2)/df),df)
                    else:probability=gamma.sf(cut,value,scale=mu/value)
                    terms.append(float(np.mean((probability-(y>=cut))**2)))
                result[gid]=float(np.mean(terms))
            else:result[gid]=float(np.mean(np.abs(draws-y[:,None]).mean(axis=1)-draws@CRPS_WEIGHTS))
    return result


def fit_value(observations,name,baseline,means):
    if name in BINARY:
        actual=np.concatenate([v for _,v in observations[name]])
        return float(np.clip((actual.sum()+100*baseline)/(len(actual)+100),*BOUNDS[name]))
    objective=lambda v:float(np.mean(list(losses(observations,name,v,means).values())))
    if name=='rushing_distribution':
        # Both candidates and the objective are fixed on training games.
        candidates=[baseline]+[{'sd':sd,'df':df} for df in [0.,3.,4.,6.,10.]
            for sd in [4.,4.5,5.,5.5,6.,6.5,7.]]
        base_tail=np.mean(list(losses(observations,name,baseline,means,tail=True).values()))
        candidates=[v for v in candidates if np.mean(list(losses(observations,name,v,means,tail=True).values()))<=base_tail]
        return min(candidates,key=objective)
    fit=minimize_scalar(objective,bounds=BOUNDS[name],method='bounded',options={'xatol':.01})
    # Retain the incumbent if optimization did not improve training loss.
    return float(fit.x) if objective(fit.x)<objective(baseline) else baseline


def independent_gate(before,after,*,minimum_games=10,minimum_relative_gain=.002,seed=961):
    games=sorted(set(before)&set(after))
    if len(games)<minimum_games:return {'accepted':False,'reason':'insufficient independent games','games':len(games)}
    base=np.array([before[g] for g in games]);new=np.array([after[g] for g in games]);difference=new-base
    # Cluster bootstrap over games, not correlated plays. All candidates are
    # fixed before this block. Bonferroni across the supported family controls
    # the per-run chance of activating an apparent win in one of many tests.
    rng=np.random.default_rng(seed);draws=rng.integers(len(games),size=(20000,len(games)))
    upper=float(np.quantile(difference[draws].mean(axis=1),1-.05/(3*len(SUPPORTED))))
    relative=float(-difference.mean()/max(abs(base.mean()),1e-12))
    return {'accepted':bool(upper<0 and relative>=minimum_relative_gain),'games':len(games),
        'baseline_loss':float(base.mean()),'candidate_loss':float(new.mean()),
        'relative_gain':relative,'familywise_95pct_upper_loss_change':upper,
        'reason':'passed independent component validation' if upper<0 and relative>=minimum_relative_gain else 'improvement not established',
        'game_loss_changes':{g:float(d) for g,d in zip(games,difference)}}


def learn_components(frame,sources,root=ROOT):
    # Archive week/season identities are supplied by the source. Never treat
    # plays from the same week as independent fitting/selection/test blocks.
    if not {'season','week'}<=set(frame):raise ValueError('Season/week identities required')
    blocks=frame[['season','week']].drop_duplicates().sort_values(['season','week']).to_numpy()
    if len(blocks)<3:raise ValueError('At least three distinct completed weeks required')
    select_block,test_block=map(tuple,blocks[-2:]);keys=list(zip(frame.season,frame.week))
    selection=frame.loc[[k==select_block for k in keys]];test=frame.loc[[k==test_block for k in keys]]
    training=frame.loc[[k not in {select_block,test_block} for k in keys]]
    groups=[training,selection,test]
    if min(g.game_id.nunique() for g in groups)<10:raise ValueError('At least ten games per chronological block required')
    if not training.game_date.max()<selection.game_date.min()<=selection.game_date.max()<test.game_date.min():
        raise ValueError('NFL component blocks overlap in time')
    all_ids=[set(g.game_id) for g in groups]
    if any(all_ids[i]&all_ids[j] for i in range(3) for j in range(i)):raise ValueError('Game overlap between blocks')
    validation_start=test.game_date.min().date().isoformat()
    root=Path(root);ledger_path=root/'evaluated_component_blocks.json'
    ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'blocks':{}}
    block_key=str(int(test_block[0]))+'-'+str(int(test_block[1]))
    if block_key in ledger['blocks']:
        previous=json.loads((root/'component_reports'/(ledger['blocks'][block_key]+'.json')).read_text())
        active=model_for_date((test.game_date.max()+pd.Timedelta(days=1)).date().isoformat(),root)
        status=dict(previous,status='already evaluated; waiting for new independent week',
                    accepted_components=[],active_version=active['version'] if active else None)
        atomic_json(root/'component_status.json',status)
        return status
    incumbent=model_for_date(validation_start,root)
    prior=dict(incumbent['parameters']) if incumbent else {}
    base=dict(DEFAULTS,**prior)
    old=block_samples(training);choose=block_samples(selection);actual=block_samples(test)
    metrics={};accepted={}
    for name in SUPPORTED:
        count=lambda obs:sum(len(values) for _,values in obs[name])
        if min(count(obs) for obs in (old,choose,actual))<50:
            metrics[name]={'accepted':False,'reason':'missing or insufficient observed events',
                'training_count':count(old),'selection_count':count(choose),'validation_count':count(actual)};continue
        means=means_from_training(old,name) if name in {'rushing_distribution','receiving_shape'} else {}
        baseline=({'sd':base['rushing_sd'],'df':base['rushing_df']} if name=='rushing_distribution' else base[name])
        fitted=fit_value(old,name,baseline,means)
        before=losses(choose,name,baseline,means);after=losses(choose,name,fitted,means)
        if np.mean(list(after.values()))>=np.mean(list(before.values())):
            metrics[name]={'accepted':False,'reason':'rejected on selection games','baseline':baseline,'fitted':fitted};continue
        final=independent_gate(losses(actual,name,baseline,means),losses(actual,name,fitted,means))
        if name in {'rushing_distribution','receiving_shape'}:
            selection_tail=np.mean(list(losses(choose,name,fitted,means,tail=True).values()))
            baseline_tail=np.mean(list(losses(choose,name,baseline,means,tail=True).values()))
            tail_gate=independent_gate(losses(actual,name,baseline,means,tail=True),losses(actual,name,fitted,means,tail=True))
            final['tail_validation']=tail_gate
            final['accepted']=bool(final['accepted'] and selection_tail<=baseline_tail and tail_gate['accepted'])
        metrics[name]=dict(final,baseline=baseline,fitted=fitted,training_count=count(old),selection_count=count(choose),validation_count=count(actual))
        if final['accepted']:
            if name=='rushing_distribution':accepted.update(rushing_sd=fitted['sd'],rushing_df=fitted['df'])
            else:accepted[name]=fitted
    report={'schema':1,'status':'accepted' if accepted else 'no component passed',
        'validation_kind':'independent conditional-event components','parameters':dict(prior,**accepted),'players':incumbent['players'] if incumbent else {},
        'accepted_components':sorted(accepted),'component_validation':metrics,'sources':sources,
        'training_games':int(training.game_id.nunique()),'selection_games':int(selection.game_id.nunique()),
        'validation_games':int(test.game_id.nunique()),'training_through':training.game_date.max().date().isoformat(),
        'selection_through':selection.game_date.max().date().isoformat(),
        'validation_from':validation_start,'validation_through':test.game_date.max().date().isoformat(),
        'parent_version':incumbent['version'] if incumbent else None,'engine_sha256':engine_digest(),
        'remaining_scope':{'player_roles':'requires longer per-player histories and independent opportunity validation',
            'joint_correlations':'requires frozen full-game replay validation','kicking_and_defense':'component activation only where observed flags and sample sizes pass'},
        'limitations':['Conditional event distribution validation, not whole-game fantasy accuracy or ROI validation.',
            'Existing engine event-support limitations are preserved; unknown actual events are never zero-filled.',
            'Current published archives may contain later statistical corrections; this historical trial is retrospective.']}
    report['version']=digest(report)[:16]
    root=Path(root);atomic_json(root/'component_reports'/(report['version']+'.json'),report)
    if accepted:
        index_path=root/'index.json';index=json.loads(index_path.read_text()) if index_path.exists() else {'schema':1,'versions':[]}
        # Once a holdout week has been used for activation decisions, do not
        # keep retesting it against successive incumbents or revised archives.
        for item in index['versions']:
            if item['validation_through']>=report['validation_from']:
                active=model_for_date((test.game_date.max()+pd.Timedelta(days=1)).date().isoformat(),root)
                status=dict(report,status='already evaluated; waiting for new independent week',
                            accepted_components=[],active_version=active['version'] if active else None)
                atomic_json(root/'component_status.json',status)
                return status
        name=report['version']+'.json';atomic_json(root/'versions'/name,report)
        index['versions'].append({'file':name,'validation_through':report['validation_through'],'sha256':digest(report)})
        atomic_json(index_path,index)
    ledger['blocks'][block_key]=report['version'];atomic_json(ledger_path,ledger)
    active=model_for_date((test.game_date.max()+pd.Timedelta(days=1)).date().isoformat(),root)
    status=dict(report,active_version=active['version'] if active else None)
    atomic_json(root/'component_status.json',status)
    return status


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',default='data/pbp');parser.add_argument('--output-root',default=str(ROOT))
    args=parser.parse_args();frame,sources=load_archives(Path(args.archives).glob('*.csv.gz'))
    report=learn_components(frame,sources,args.output_root)
    print(json.dumps({key:report[key] for key in ['status','accepted_components','training_games','selection_games','validation_games']},indent=2))

if __name__=='__main__':main()
