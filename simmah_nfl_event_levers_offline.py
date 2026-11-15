"""Offline training-only gain-tail and fourth-down candidates. No live imports."""
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm,gamma

VERSION='nfl-event-levers-offline-v1'
COLUMNS=['season','game_id','play_id','play_type','qtr','down','ydstogo','yardline_100',
         'game_seconds_remaining','score_differential','qb_kneel','qb_spike','qb_scramble',
         'two_point_attempt','extra_point_attempt','complete_pass','yards_gained',
         'rush_touchdown','pass_touchdown']


def read_season(root,season):
    # Guard before any read; 2025/2026 are deliberately not accepted.
    if season not in (2022,2023,2024):raise ValueError('Locked or unsupported season')
    p=Path(root)/f'play_by_play_{season}.csv.gz'
    f=pd.read_csv(p,usecols=COLUMNS,low_memory=False)
    if set(f.season.dropna().astype(int))!={season}:raise ValueError('Season metadata mismatch')
    if f[['game_id','play_id']].isna().any().any() or f.duplicated(['game_id','play_id']).any():
        raise ValueError('Missing/duplicate game-play identity')
    return f,{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'rows':len(f)}


def common(f):
    return (f.qtr.between(1,4)&f.qb_kneel.eq(0)&f.qb_spike.eq(0)&f.two_point_attempt.eq(0)&
            f.extra_point_attempt.eq(0)&f.yardline_100.between(1,100))


def gains(f,kind):
    mask=common(f)&f.yards_gained.between(-99,100)
    if kind=='run':mask &= f.play_type.eq('run')&f.qb_scramble.eq(0)
    elif kind=='completion':mask &= f.play_type.eq('pass')&f.complete_pass.eq(1)
    else:raise ValueError('Unknown gain kind')
    out=f.loc[mask].copy()
    if not np.allclose(out.yards_gained,np.rint(out.yards_gained)):
        raise ValueError('Integer recorded gains required')
    return out


def fit_gain(frame,kind):
    if not set(frame.season.unique())<= {2022,2023}:raise ValueError('Fit is restricted to 2022-2023')
    f=gains(frame,kind)
    if len(f)<100:raise ValueError('Insufficient gain observations')
    support=np.arange(-99,101,dtype=float);g=f.yards_gained.to_numpy(int)
    td=f['rush_touchdown' if kind=='run' else 'pass_touchdown'].eq(1).to_numpy()
    censored=td&np.isclose(g,f.yardline_100.to_numpy(float))
    exact=np.bincount(g[~censored]+99,minlength=200).astype(float)
    thresholds=np.bincount(g[censored]+99,minlength=200).astype(float)
    # Interval-censored TD gain: latent distance is >= available field.
    # Weak total Dirichlet mass 1 regularizes otherwise unidentified cells.
    prior=np.full(200,1/200);p=(exact+prior)/(exact.sum()+1)
    converged=False
    for iteration in range(2000):
        tail=np.cumsum(p[::-1])[::-1]
        imputed=p*np.cumsum(thresholds/np.maximum(tail,1e-300))
        new=(exact+imputed+prior)/(len(f)+1)
        if np.max(np.abs(new-p))<1e-11:
            p=new;converged=True;break
        p=new
    if not np.isclose(p.sum(),1):raise ValueError('Invalid fitted PMF')
    return {'version':VERSION,'kind':kind,'support':support.tolist(),'probabilities':p.tolist(),
        'latent_mean':float(p@support),'records':len(f),'censored_touchdowns':int(censored.sum()),
        'iterations':iteration+1,'converged':converged,'fit_seasons':[2022,2023],
        'assumption':'Within event type, latent gain independent of field position; conditional mechanics only, not validated player/team model'}


def sample_gain(model,uniform,environment,*,target_mean=None):
    u=np.asarray(uniform,float);env=np.asarray(environment,float)
    if np.any((u<0)|(u>=1)) or np.any(~np.isfinite(u)) or np.any(~np.isfinite(env)) or np.any(env<=0):
        raise ValueError('Invalid shared random inputs')
    if model.get('kind') not in {'run','completion'}:raise ValueError('Unknown gain kind')
    p=np.asarray(model['probabilities'],float);support=np.asarray(model['support'],float)
    if p.ndim!=1 or p.shape!=support.shape or not len(p) or not np.isfinite(p).all() or not np.isfinite(support).all() or (p<0).any() or not np.isclose(p.sum(),1):
        raise ValueError('Invalid gain distribution')
    raw=support[np.searchsorted(np.cumsum(p),u,side='right').clip(0,len(p)-1)]
    if target_mean is not None:
        if not np.isfinite(target_mean) or target_mean<=0 or model['latent_mean']<=0:raise ValueError('Invalid mean target')
        raw=raw*(target_mean/model['latent_mean'])
    if model['kind']=='run':return np.clip(raw*np.sqrt(env),-5,65)
    return np.clip(raw*env,0,85)


def fourth_rows(f):
    mask=(common(f)&f.down.eq(4)&f.play_type.isin(['run','pass','punt','field_goal'])&
          f.ydstogo.between(0,100)&f.game_seconds_remaining.between(0,3600)&
          f.score_differential.notna())
    x=f.loc[mask].copy();x['go']=x.play_type.isin(['run','pass']).astype(int)
    return x


def fourth_features(f):
    if 'down' not in f or not f.down.eq(4).all():raise ValueError('Fourth-down states required')
    if not (f[['yardline_100','ydstogo','game_seconds_remaining','score_differential','qtr']].notna().all().all()
            and f.yardline_100.between(0,100).all() and f.ydstogo.between(0,100).all()
            and f.game_seconds_remaining.between(0,3600).all() and f.qtr.between(1,4).all()):
        raise ValueError('Valid pre-play fourth-down state required')
    territory=np.select([f.yardline_100.lt(5),f.yardline_100.lt(35),f.yardline_100.le(50)],
                        ['inside5','opp35_5','opp50_35'],default='own_half')
    bucket=np.char.add(np.char.add(territory.astype(str),'_'),np.where(f.ydstogo.le(2),'short','other'))
    endhalf=f.qtr.eq(2)&f.game_seconds_remaining.le(1920)&f.game_seconds_remaining.ge(1800)
    neutral=f.score_differential.abs().le(8)&f.game_seconds_remaining.gt(300)&~endhalf
    script=np.select([f.game_seconds_remaining.le(300)&f.score_differential.lt(0),endhalf,neutral],
                     ['late_trailing','end_half','neutral'],default='other')
    return bucket,script,neutral.to_numpy()


def fit_fourth(frame):
    if not set(frame.season.unique())<={2022,2023}:raise ValueError('Fit is restricted to 2022-2023')
    x=fourth_rows(frame);bucket,script,_=fourth_features(x)
    bases={};groups={}
    for b in np.unique(bucket):
        loc=bucket==b;n=int(loc.sum());success=int(x.go.to_numpy()[loc].sum())
        bases[str(b)]={'n':n,'go':success,'p':(success+1)/(n+2)}
        for state in np.unique(script[loc]):
            g=loc&(script==state);groups[str(b)+'|'+str(state)]={'n':int(g.sum()),'go':int(x.go.to_numpy()[g].sum())}
    return {'version':VERSION,'fit_seasons':[2022,2023],'records':len(x),
        'prior_strength':20.,'global_probability':float((x.go.sum()+1)/(len(x)+2)),
        'base_buckets':bases,'state_buckets':groups}


def predict_fourth(model,states):
    buckets,scripts,_=fourth_features(states);p=[]
    for b,s in zip(buckets,scripts):
        base=model['base_buckets'].get(str(b))
        if base is None:raise ValueError('No training support for fourth-down territory')
        group=model['state_buckets'].get(str(b)+'|'+str(s),{'n':0,'go':0})
        p.append((group['go']+model['prior_strength']*base['p'])/(group['n']+model['prior_strength']))
    return np.asarray(p)


def baseline_fourth(states):
    fourth_features(states)
    return (states.yardline_100.lt(5)|(states.score_differential.lt(0)&states.game_seconds_remaining.lt(180))).to_numpy(float)


def evaluate_fourth(model,test):
    if set(test.season.unique())!={2024}:raise ValueError('Only 2024 conditional evaluation is unlocked')
    f=fourth_rows(test);p=predict_fourth(model,f);y=f.go.to_numpy();base=baseline_fourth(f)
    b,s,neutral=fourth_features(f);table=[]
    for name in np.unique(b):
        for label,m in [('all',b==name),('neutral',(b==name)&neutral)]:
            if not m.any():continue
            table.append({'bucket':str(name),'slice':label,'n':int(m.sum()),'observed_go':float(y[m].mean()),
                          'candidate_go_probability':float(p[m].mean()),'baseline_go':float(base[m].mean())})
    def metric(q):
        clipped=np.clip(q,1e-6,1-1e-6)
        return {'brier':float(np.mean((q-y)**2)),
            'log_loss_with_1e6_clip':float(-np.mean(y*np.log(clipped)+(1-y)*np.log1p(-clipped))),
            'mean_go_probability':float(q.mean())}
    codes,game_ids=pd.factorize(f.game_id)
    sizes=np.bincount(codes);rng=np.random.default_rng(41298)
    draws=rng.integers(0,len(game_ids),size=(2000,len(game_ids)))
    delta=(p-y)**2-(model['global_probability']-y)**2
    blocks=np.bincount(codes,weights=delta)
    boot=blocks[draws].sum(axis=1)/sizes[draws].sum(axis=1)
    interval={'brier_delta_vs_global':float(delta.mean()),'ci95':np.quantile(boot,[.025,.975]).tolist(),
        'resamples':2000,'unit':'whole games','seed':41298,'scope':'2024 tuning diagnostic, not a holdout promotion gate'}
    return {'n':len(f),'games':f.game_id.nunique(),'observed_go':float(y.mean()),'paired_game_bootstrap':interval,
            'baseline_policy':metric(base),'global_league_rate':metric(np.full(len(f),model['global_probability'])),
            'candidate':metric(p),'slices':table,
            'scope':'Observed pre-play opportunities; no simulated conversion, punt, score or drive claim'}


def evaluate_gains(models,test,draws=64,seeds=(17311,29107)):
    if set(test.season.unique())!={2024}:raise ValueError('Only 2024 conditional evaluation is unlocked')
    if not isinstance(draws,int) or draws<1 or not seeds:raise ValueError('Positive draws and at least one seed required')
    results={}
    for kind in ['run','completion']:
        f=gains(test,kind);d=f.yardline_100.to_numpy(float);actual=f.yards_gained.to_numpy(float)
        games=int(test.game_id.nunique());target=4.494838753204696 if kind=='run' else 10.913338511221028
        totals={name:[] for name in ['baseline','empirical_censor_aware','empirical_mean_matched']}
        for seed in seeds:
            rng=np.random.default_rng(seed+(0 if kind=='run' else 1));u=rng.random((len(f),draws))
            env=np.clip(1+rng.normal(0,.1,u.shape),.75,1.3)
            raw=(np.clip(norm.ppf(u,loc=target,scale=5.5)*np.sqrt(env),-5,65) if kind=='run'
                 else np.clip(gamma.ppf(u,a=1.5,scale=target/1.5)*env,0,85))
            arrays={'baseline':raw,'empirical_censor_aware':sample_gain(models[kind],u,env),
                    'empirical_mean_matched':sample_gain(models[kind],u,env,target_mean=target)}
            for name,gain in arrays.items():
                g=np.minimum(gain,d[:,None])
                item={'mean_gain':float(g.mean()),'non_red_zone_td_per_game_proxy':float(((g>=d[:,None])&(d[:,None]>20)).sum()/draws/games)}
                for t in [20,30,40]:
                    item[f'gain_{t}_rate']=float((g>=t).mean())
                    eligible=d>=t
                    item[f'gain_{t}_eligible_rate']=float((g[eligible]>=t).mean()) if eligible.any() else None
                totals[name].append(item)
        observed={'records':len(f),'games':games,'plays_per_game':len(f)/games,'mean_gain':float(actual.mean()),
            'non_red_zone_td_per_game':float((f['rush_touchdown' if kind=='run' else 'pass_touchdown'].eq(1)&f.yardline_100.gt(20)).sum()/games)}
        for t in [20,30,40]:
            observed[f'gain_{t}_rate']=float((actual>=t).mean())
            observed[f'gain_{t}_eligible_rate']=float((actual[d>=t]>=t).mean()) if (d>=t).any() else None
        results[kind]={'observed':observed,'candidates':{name:{k:(float(np.mean([r[k] for r in rs])) if rs[0][k] is not None else None) for k in rs[0]} for name,rs in totals.items()},'seed_results':totals}
    return {'scope':'Conditional on observed 2024 play type and field location; fixed opportunity counts, not a full-game replay',
            'draws_per_observed_play':draws,'seeds':list(seeds),'results':results}


def fit_rushing_body(model,train):
    """Training-only mean constraint; preserve mass outside gains 1..6 exactly.

    Uses the actual training field-position distribution and the fixed clipped
    environment law. No 2024 YPC target or outcome enters this calibration.
    """
    if set(train.season.unique())!={2022,2023} or model.get('fit_seasons')!=[2022,2023] or model.get('kind')!='run':
        raise ValueError('Rushing body fit requires 2022-2023 only')
    from scipy.optimize import brentq
    from copy import deepcopy
    f=gains(train,'run');support=np.asarray(model['support']);p=np.asarray(model['probabilities'])
    if len(f)<100:raise ValueError('Insufficient training runs')
    d=np.sort(f.yardline_100.to_numpy(float));own=np.sort(100-d)
    def expected_min(values,limits):
        prefix=np.r_[0.,np.cumsum(limits)];k=np.searchsorted(limits,values,side='left')
        return (prefix[k]+values*(len(limits)-k))/len(limits)
    # Deterministic Gaussian quadrature; clips exactly as the event sampler.
    nodes,w=np.polynomial.hermite.hermgauss(64);env=np.clip(1+.1*np.sqrt(2)*nodes,.75,1.30)
    expected=np.zeros(len(support))
    for e,weight in zip(env,w/np.sqrt(np.pi)):
        raw=np.clip(support*np.sqrt(e),-5,65)
        expected+=weight*np.where(raw>=0,expected_min(np.maximum(raw,0),d),-expected_min(np.maximum(-raw,0),own))
    body=(support>=1)&(support<=6);mass=p[body].sum();target=float(f.yards_gained.mean())
    def adjusted(tau):
        out=p.copy();z=tau*support[body];z-=z.max();b=p[body]*np.exp(z);out[body]=mass*b/b.sum();return out
    low=float(adjusted(-100)@expected);high=float(adjusted(100)@expected)
    if not low<=target<=high:raise ValueError('Training mean infeasible with short-body-only lever')
    tau=float(brentq(lambda t:adjusted(t)@expected-target,-100,100,xtol=1e-12))
    out=deepcopy(model);out['probabilities']=adjusted(tau).tolist();out['latent_mean']=float(adjusted(tau)@support)
    out['body_calibration']={'fit_seasons':[2022,2023],'records':len(f),'target_observed_training_ypc':target,
        'expected_before':float(p@expected),'expected_after':float(adjusted(tau)@expected),'tilt':tau,
        'adjusted_support':[1,6],'outside_body_mass_max_change':float(np.max(np.abs(adjusted(tau)[~body]-p[~body]))),
        'environment_quadrature_nodes':64,'scope':'Training-field-position mean constraint, not full-game calibration'}
    return out
