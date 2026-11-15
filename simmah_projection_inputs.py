"""Fit opportunity and passing inputs to the posted slate point projections.

Independent pilot games fit event parameters; final simulation paths are fresh.
Fantasy scores are never rescaled, bootstrapped, or fitted to contest returns.
Parameter bounds and residuals are explicit; this does not guarantee exact means.
"""
import numpy as np
import pandas as pd
import time

VERSION='projection-event-input-fit-v2-final-context'


def fit_projection_inputs(pool,roles,platform,scorer,pilot_n=1024,iterations=8,progress=None,learned_parameters=None,
                          correlation_strength=1.,weather_by_team=None,market_gain=None,initial_parameters=None,
                          resume_state=None,save_state=None):
    from simmah_nfl_engine import simulate_stat_lines
    rows=pool.to_dict('records')
    targets={str(r['Name']):max(0,float(r.get('Projection',0))) for r in rows}
    positions={str(r['Name']):str(r.get('Position','')).upper().split('/')[0] for r in rows}
    params={name:{'pass_gain':1.,'opportunity':1.,'skill_gain':1.} for name in targets}
    if initial_parameters:
        params={name:dict(values,**initial_parameters.get(name,{})) for name,values in params.items()}
    first=None;last=None;best_loss=float("inf");best_params=None;best_means=None
    next_iteration=0
    if resume_state is not None:
        next_iteration=int(resume_state['next_iteration'])
        if not 0<=next_iteration<=iterations+1:
            raise ValueError('Invalid projection-fit checkpoint iteration')
        params=resume_state['params'];first=resume_state['first']
        best_loss=resume_state['best_loss'];best_params=resume_state['best_params'];best_means=resume_state['best_means']
        if set(params)!=set(targets) or set(best_means)!=set(targets):
            raise ValueError('Projection-fit checkpoint players differ')
    started=time.perf_counter();completed=0
    def notify(fraction,text):
        if progress:
            elapsed=time.perf_counter()-started
            eta=(f"; fit ETA ~{elapsed/completed*(iterations+1-iteration-fraction):.0f}s" if completed else '; estimating fit time')
            progress((iteration+fraction)/(iterations+1),
                f"Fitting projections: pass {iteration+1}/{iterations+1} — {text} (elapsed {elapsed:.0f}s{eta}; final outcomes follow)")
    for iteration in range(next_iteration,iterations+1):
        # Common pilot seed reduces Monte Carlo noise between parameter updates.
        # This seed is independent of the caller's evaluation/construction RNG.
        stats=simulate_stat_lines(pool,roles,np.random.default_rng(73019),pilot_n,projection_inputs=params,scoring_platform=platform,
            correlation_strength=correlation_strength,weather_by_team=weather_by_team,market_gain=market_gain,
            progress=notify if progress else None,learned_parameters=learned_parameters)
        means={name:float(np.mean(scorer(dict(line,is_defense=int(positions[name] in {'D','DST','DEF'})),platform))) for name,line in stats.items()}
        if first is None:first=means.copy()
        last=means
        offense=[name for name in targets if positions[name] in {'QB','RB','WR','TE'}]
        loss=sum((means[name]-targets[name])**2/max(targets[name],1) for name in offense)/max(len(offense),1)
        if loss<best_loss:
            best_loss=loss;best_params={name:dict(values) for name,values in params.items()};best_means=means.copy()
        for name,target in (targets.items() if iteration<iterations else []):
            pos=positions[name]
            ratio=np.clip(target/max(means[name],.05),.2,5.)
            if pos=='QB':
                params[name]['pass_gain']=float(np.clip(params[name]['pass_gain']*ratio**.45,.25,3.))
            elif pos in {'RB','WR','TE'}:
                params[name]['opportunity']=float(np.clip(params[name]['opportunity']*ratio**.40,.02,50.))
                params[name]['skill_gain']=float(np.clip(params[name]['skill_gain']*ratio**.20,.25,2.5))
        completed+=1
        if save_state:
            save_state(dict(next_iteration=iteration+1,params=params,first=first,best_loss=best_loss,
                            best_params=best_params,best_means=best_means))
    params=best_params;last=best_means
    report=pd.DataFrame([{'Name':name,'Projection':targets[name],'Before Calibration':first[name],
        'Pilot Mean':last[name],'Pilot Difference':last[name]-targets[name],
        'Passing Input':params[name]['pass_gain'],'Opportunity Input':params[name]['opportunity'],'Skill Gain Input':params[name]['skill_gain'],
        'Calibration Status':'Event inputs fitted' if positions[name] in {'QB','RB','WR','TE'} else 'Unfitted defense/kicker'} for name in targets])
    if progress:progress(1.,"Projection fitting complete")
    return params,report

