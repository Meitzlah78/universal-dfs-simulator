"""NFL event/role candidates and full-engine temporal replay promotion.

Full-game model promotion requires complete later frozen replays. Separately
validated conditional-event components use their own three-block activation path.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent / 'data' / 'nfl_models'
SCHEMA = 1
# Every tunable parameter acts before shared stat/score accounting.
DEFAULTS = dict(pass_rate=.58, sack_rate=.065, interception_rate=.021,
    completion_rate=.64, receiving_yards=11.2, receiving_shape=1.5,
    rushing_yards=4.35, rushing_sd=5.5, rushing_df=0., fumble_loss_rate=.0064,
    extra_point_rate=.9468, two_point_rate=.097, two_point_pass_share=.55,
    two_point_pass_success=.4437, two_point_run_success=.5466,
    defensive_return_td_rate=.08, field_goal_logit_offset=0.,pace_sd=.09,environment_sd=.10,opportunity_concentration=0.)
BOUNDS = dict(pass_rate=(.44,.70), sack_rate=(.02,.15), interception_rate=(.006,.05),
    completion_rate=(.52,.76), receiving_yards=(5.,20.), receiving_shape=(.5,5.),
    rushing_yards=(2.,8.5), rushing_sd=(3.,9.), rushing_df=(0.,30.), fumble_loss_rate=(.001,.03),
    extra_point_rate=(.8,.99), two_point_rate=(.02,.25), two_point_pass_share=(.2,.8),
    two_point_pass_success=(.2,.8), two_point_run_success=(.2,.8),
    defensive_return_td_rate=(.01,.3), field_goal_logit_offset=(-.5,.5),
    pace_sd=(.02,.2),environment_sd=(.02,.25),opportunity_concentration=(0.,200.))
ROLE_FIELDS = ('pass_attempts','completions','pass_yards','pass_tds','interceptions',
               'carries','rush_yards','rush_tds','targets','receptions','rec_yards','rec_tds')


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=path.parent,prefix=path.name+'.',suffix='.tmp')
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def validate_parameters(parameters):
    if not isinstance(parameters,dict) or set(parameters)-set(DEFAULTS):
        raise ValueError('Unknown NFL learned parameters')
    for name,value in parameters.items():
        lo,hi=BOUNDS[name]
        if name=='rushing_df' and value!=0 and (not isinstance(value,(int,float)) or value<=2):
            raise ValueError('Rushing tail degrees of freedom must be zero or exceed two')
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value) or not lo<=value<=hi:
            raise ValueError('Invalid NFL learned parameter: '+name)
    return dict(DEFAULTS,**parameters)


def load_archives(paths):
    frames=[];sources=[]
    for path in sorted(map(Path,paths)):
        raw=path.read_bytes();frame=pd.read_csv(path)
        needed={'game_id','play_id','game_date','qtr','game_seconds_remaining','play_type','posteam','defteam',
                'yards_gained','sack','interception','complete_pass','two_point_attempt','extra_point_attempt'}
        if frame.empty or not needed<=set(frame):raise ValueError('Incomplete NFL archive: '+str(path))
        dates=pd.to_datetime(frame.game_date,utc=True,errors='raise')
        if dates.isna().any():raise ValueError('Missing NFL game dates')
        frame=frame.copy();frame['game_date']=dates
        if frame[['game_id','play_id']].isna().any().any():raise ValueError('Missing game/play identity')
        for game,rows in frame.groupby('game_id'):
            if rows.game_date.nunique()!=1:raise ValueError('Conflicting game dates: '+str(game))
            reg=rows[pd.to_numeric(rows.qtr,errors='coerce').between(1,4)]
            if not pd.to_numeric(reg.game_seconds_remaining,errors='coerce').eq(0).any():
                raise ValueError('Missing regulation-end marker: '+str(game))
        sources.append({'path':path.name,'sha256':sha256(raw).hexdigest(),'rows':len(frame)})
        frames.append(frame)
    if not frames:raise ValueError('No NFL archives')
    all_rows=pd.concat(frames,ignore_index=True)
    if all_rows.duplicated(['game_id','play_id']).any():raise ValueError('Overlapping NFL archives/game-play IDs')
    return all_rows,sources


def regulation(frame):
    return frame.loc[pd.to_numeric(frame.qtr,errors='coerce').between(1,4)].copy()


def flag(frame,column):
    if column not in frame:raise ValueError('Missing '+column)
    values=pd.to_numeric(frame[column],errors='coerce')
    if values.isna().any() or not values.isin([0,1]).all():raise ValueError('Missing/invalid '+column)
    return values.to_numpy(float)


def event_samples(frame):
    """Known-event denominators only; missing optional flags are never zeros."""
    reg=regulation(frame)
    plays=reg.loc[reg.play_type.isin(['pass','run'])]
    plays=plays.loc[(flag(plays,'two_point_attempt')==0)&(flag(plays,'extra_point_attempt')==0)]
    ordinary=reg.loc[reg.play_type.notna()&~reg.play_type.eq('no_play')]
    passing=plays[plays.play_type.eq('pass')];running=plays[plays.play_type.eq('run')]
    clean=passing.loc[flag(passing,'sack')==0]
    throws=clean.loc[flag(clean,'interception')==0]
    completed=throws.loc[flag(throws,'complete_pass')==1]
    # Neutral script for the fallback pass propensity; in-game margin adjustment
    # remains in the engine and is not fitted away.
    neutral=plays
    if 'score_differential' in plays:
        neutral=plays[pd.to_numeric(plays.score_differential,errors='coerce').abs().le(7)]
    samples={'pass_rate':neutral.play_type.eq('pass').to_numpy(float),
        'sack_rate':flag(passing,'sack'),'interception_rate':flag(clean,'interception'),
        'completion_rate':flag(throws,'complete_pass'),
        'receiving_yards':pd.to_numeric(completed.yards_gained,errors='coerce').to_numpy(float),
        'rushing_yards':pd.to_numeric(running.yards_gained,errors='coerce').to_numpy(float)}
    missing={}
    def known_flag(rows,column):
        if column not in rows:raise ValueError('Missing '+column)
        values=pd.to_numeric(rows[column],errors='coerce')
        if not values.dropna().isin([0,1]).all():raise ValueError('Invalid '+column)
        return values.to_numpy(float)
    for name,extract in {
        'fumble_loss_rate':lambda:known_flag(plays.loc[(plays.play_type.eq('run'))|plays.sack.eq(1)|plays.complete_pass.eq(1)],'fumble_lost'),
        'extra_point_rate':lambda:reg.loc[reg.extra_point_attempt.eq(1),'extra_point_result'].map({'good':1.,'failed':0.,'blocked':0.}).to_numpy(float),
        'two_point_rate':lambda:flag(reg.loc[reg.extra_point_attempt.eq(1)|reg.two_point_attempt.eq(1)],'two_point_attempt'),
        'two_point_pass_share':lambda:reg.loc[reg.two_point_attempt.eq(1),'play_type'].map({'pass':1.,'run':0.}).to_numpy(float),
        'two_point_pass_success':lambda:reg.loc[reg.two_point_attempt.eq(1)&reg.play_type.eq('pass'),'two_point_conv_result'].map({'success':1.,'failure':0.}).to_numpy(float),
        'two_point_run_success':lambda:reg.loc[reg.two_point_attempt.eq(1)&reg.play_type.eq('run'),'two_point_conv_result'].map({'success':1.,'failure':0.}).to_numpy(float),
        'defensive_return_td_rate':lambda:known_flag(ordinary.loc[ordinary.interception.eq(1)|pd.to_numeric(ordinary['fumble_lost'],errors='coerce').eq(1)],'return_touchdown'),
    }.items():
        try:
            values=extract()
            known=np.isfinite(values)
            if not known.all():missing[name]='Excluded '+str(int((~known).sum()))+' unknown event records; not treated as zeros'
            values=values[known]
            if not len(values):raise ValueError('Missing observations')
            samples[name]=values
        except (KeyError,ValueError) as exc:missing[name]=str(exc)
    for name,values in samples.items():
        if not len(values) or not np.isfinite(values).all():raise ValueError('Missing event sample: '+name)
    return samples,missing


def player_profiles(frame):
    """Stable GSIS identities; no joins on abbreviated display names."""
    reg=regulation(frame)
    plays=reg.loc[reg.play_type.isin(['pass','run'])&reg.two_point_attempt.eq(0)&reg.extra_point_attempt.eq(0)]
    profiles={}
    for idcol,namecol,mask,fields in [
        ('passer_player_id','passer_player_name',plays.play_type.eq('pass')&plays.sack.eq(0),
         {'pass_attempts':None,'completions':'complete_pass','pass_yards':'completed_yards','pass_tds':'pass_touchdown','interceptions':'interception'}),
        ('receiver_player_id','receiver_player_name',plays.play_type.eq('pass')&plays.sack.eq(0)&plays.interception.eq(0),
         {'targets':None,'receptions':'complete_pass','rec_yards':'completed_yards','rec_tds':'pass_touchdown'}),
        ('rusher_player_id','rusher_player_name',plays.play_type.eq('run'),
         {'carries':None,'rush_yards':'yards_gained','rush_tds':'rush_touchdown'}),
    ]:
        if not {idcol,namecol,*[v for v in fields.values() if v and v!='completed_yards']}<=set(plays):continue
        sub=plays.loc[mask&plays[idcol].notna()].copy()
        sub['completed_yards']=pd.to_numeric(sub.yards_gained,errors='coerce').where(sub.complete_pass.eq(1),0.)
        for pid,rows in sub.groupby(idcol):
            # Do not mix players traded across teams; current-team match required.
            for team,group in rows.groupby('posteam'):
                key=str(pid)+'|'+str(team)
                profile=profiles.setdefault(key,{'player_id':str(pid),'team':str(team),'name':str(group[namecol].iloc[-1]),'game_ids':set()})
                profile['game_ids'].update(group.game_id.unique())
                for field,column in fields.items():
                    values=np.ones(len(group)) if column is None else pd.to_numeric(group[column],errors='coerce').to_numpy(float)
                    if not np.isfinite(values).all():raise ValueError('Missing player stat: '+field)
                    profile[field]=float(values.sum())
    for profile in profiles.values():
        # Denominator = team games, not only games where a player recorded a touch.
        games=plays.loc[plays.posteam.astype(str).eq(profile['team']),'game_id'].nunique()
        profile['games']=int(games);profile.pop('game_ids')
        for field in ROLE_FIELDS:profile[field]=float(profile.get(field,0.)/max(games,1))
    return profiles


def fit_candidate(frame,sources,validation_days=7,min_games=10):
    """Train strictly before the last date block, keeping whole games together."""
    dates=frame.groupby('game_id').game_date.first()
    cutoff=dates.max().normalize()-pd.Timedelta(days=validation_days-1)
    train=frame[frame.game_date<cutoff];test=frame[frame.game_date>=cutoff]
    if min(train.game_id.nunique(),test.game_id.nunique())<min_games:
        raise ValueError('Insufficient distinct training/validation games')
    old,missing_train=event_samples(train);actual,missing_test=event_samples(test)
    parameters={};metrics={}
    for name,baseline in DEFAULTS.items():
        if name in {'pace_sd','environment_sd','opportunity_concentration','rushing_df'}:
            metrics[name]={'status':'awaiting full-engine training replays','reason':'Shared-game dependence must be fitted against joint outcomes'};continue
        source={'receiving_shape':'receiving_yards','rushing_sd':'rushing_yards'}.get(name,name)
        if name=='field_goal_logit_offset':
            try:
                from scipy.optimize import minimize_scalar
                def kicks(data):
                    rows=regulation(data).loc[lambda x:x.field_goal_attempt.eq(1)]
                    distance=pd.to_numeric(rows.kick_distance,errors='coerce').to_numpy(float)
                    outcomes=rows.field_goal_result.map({'made':1.,'missed':0.,'blocked':0.}).to_numpy(float)
                    known=np.isfinite(distance)&np.isfinite(outcomes)
                    distance=distance[known];outcomes=outcomes[known]
                    if len(distance)<30:raise ValueError('Need at least 30 complete FG attempts per split')
                    probability=np.clip(.97-.005*np.maximum(distance-30,0)-.009*np.maximum(distance-45,0),.35,.98)
                    return np.log(probability/(1-probability)),outcomes
                logits,y=kicks(train);test_logits,y_test=kicks(test)
                def loss(offset,l,y):return float(np.mean(np.logaddexp(0,l+offset)-y*(l+offset)))
                estimate=float(minimize_scalar(lambda x:loss(x,logits,y),bounds=BOUNDS[name],method='bounded').x)
                before=loss(0.,test_logits,y_test);after=loss(estimate,test_logits,y_test)
                useful=after<before
                metrics[name]={'status':'candidate' if useful else 'rejected event diagnostic',
                    'baseline':0.,'fitted':estimate,'baseline_loss':before,'candidate_loss':after,
                    'training_count':len(y),'validation_count':len(y_test)}
                if useful:parameters[name]=estimate
            except (KeyError,ValueError,AttributeError) as exc:
                metrics[name]={'status':'unavailable','reason':str(exc)}
            continue
        if source not in old or source not in actual:
            metrics[name]={'status':'unavailable','reason':missing_train.get(name) or missing_test.get(name) or 'Requires complete kick results and distance replay'};continue
        values=old[source];observed=actual[source]
        minimum=50 if name not in {'rushing_yards','rushing_sd','receiving_yards','receiving_shape'} else 100
        if min(len(values),len(observed))<minimum:
            metrics[name]={'status':'insufficient sample','training_count':len(values),'validation_count':len(observed)};continue
        if name=='receiving_shape':
            estimate=float(np.mean(values)**2/max(np.var(values),1e-6))
        elif name=='rushing_sd':estimate=float(np.std(values))
        else:estimate=float((values.sum()+100*baseline)/(len(values)+100))
        estimate=float(np.clip(estimate,*BOUNDS[name]))
        # Diagnostics are conditional likelihoods; full-engine replay below is
        # the activation gate, not these per-event proxy scores.
        if source=='rushing_yards':
            mu=DEFAULTS['rushing_yards'] if name=='rushing_sd' else baseline
            base_sd=DEFAULTS['rushing_sd'];new_mu=mu if name=='rushing_sd' else estimate
            new_sd=estimate if name=='rushing_sd' else base_sd
            loss=lambda m,s:float(np.mean(np.log(s)+.5*((observed-m)/s)**2))
            before=loss(mu,base_sd);after=loss(new_mu,new_sd)
        elif source=='receiving_yards':
            # Negative/zero completed gains are legal but a gamma likelihood
            # cannot represent them. Use squared-mean / variance diagnostics;
            # only complete raw-stat replay can approve this candidate.
            stat=np.var(observed) if name=='receiving_shape' else np.mean(observed)
            before_value=DEFAULTS['receiving_yards']**2/baseline if name=='receiving_shape' else baseline
            after_value=DEFAULTS['receiving_yards']**2/estimate if name=='receiving_shape' else estimate
            before=float((stat-before_value)**2);after=float((stat-after_value)**2)
        else:
            loss=lambda p:float(-np.mean(observed*np.log(p)+(1-observed)*np.log1p(-p)))
            before=loss(baseline);after=loss(estimate)
        useful=after<before
        metrics[name]={'status':'candidate' if useful else 'rejected event diagnostic','baseline':baseline,'fitted':estimate,
                       'training_count':len(values),'validation_count':len(observed),'baseline_loss':before,'candidate_loss':after,
                       'unknown_training_records':missing_train.get(name),'unknown_validation_records':missing_test.get(name)}
        if useful:parameters[name]=estimate
    candidate={'schema':SCHEMA,'status':'awaiting full-engine replay','parameters':parameters,
        'players':{key:value for key,value in player_profiles(train).items() if value['games']>=4},
        'player_role_minimum_team_games':4,'sources':sources,'event_diagnostics':metrics,
        'training_through':train.game_date.max().date().isoformat(),
        'validation_from':test.game_date.min().date().isoformat(),'validation_through':test.game_date.max().date().isoformat(),
        'training_games':int(train.game_id.nunique()),'validation_games':int(test.game_id.nunique()),
        'source_game_ids':sorted(map(str,frame.game_id.unique())),
        'scope':['passing','rushing','receiving','volume','efficiency','variance','correlations','kicking','turnovers','defense'],
        'limitations':['Regulation only; incomplete historical kick/fumble flags are not inferred.',
                      'Event diagnostic is not full-engine prediction or DFS ROI validation.',
                      'No player/DST fantasy actuals are reconstructed from reduced archives.']}
    candidate['version']=digest(candidate)[:16]
    return candidate


def apply_player_profiles(roles,players):
    result=deepcopy(roles)
    for name,role in result.items():
        key=str(role.get('player_id',''))+'|'+str(role.get('team',''))
        profile=players.get(key)
        if profile and profile.get('games',0)>=4:
            for field in ROLE_FIELDS:
                role[field]=.75*float(role.get(field,0.))+.25*float(profile[field])
    return result


def model_for_date(as_of,root=ROOT):
    """Only immutable, fully validated versions dated before the slate load."""
    if as_of is None:return None
    day=pd.Timestamp(as_of).date().isoformat()
    index=Path(root)/'index.json'
    if not index.exists():return None
    items=json.loads(index.read_text()).get('versions',[])
    for item in sorted(items,key=lambda x:x['validation_through'],reverse=True):
        if item['validation_through']>=day:continue
        path=Path(root)/'versions'/item['file']
        if path.parent!=Path(root)/'versions':raise ValueError('Invalid NFL model path')
        model=json.loads(path.read_text())
        if digest(model)!=item['sha256'] or model.get('status')!='accepted':raise ValueError('Invalid NFL learned model')
        validate_parameters(model['parameters'])
        if model.get('engine_sha256')!=engine_digest():raise ValueError('NFL learned model requires revalidation after engine changes')
        return model
    return None


def engine_digest():
    root=Path(__file__).parent
    return digest({name:sha256((root/name).read_bytes()).hexdigest() for name in
        ('simmah_nfl_engine.py','simmah_nfl_scoring.py','simmah_nfl_learning.py','simmah_nfl_event_learning.py',
         'simmah_projection_inputs.py','simmah_market_calibration.py','simmah_weather.py',
         'simmah_matchups.py','simmah_qb_roles.py','simmah_simulation_store.py')})


def replay_losses(cases,parameters,players,*,draws=1024,seed=791):
    """Proper marginal and joint scoring of complete raw stat vectors.

    CRPS and multivariate energy scores assess distribution spread and shared
    outcomes. Raw-score losses are reported per position/stat as well as jointly.
    They do not establish contest-field accuracy or portfolio ROI.
    """
    from simmah_nfl_engine import simulate_stat_lines,STAT_KEYS
    metrics={};dates=[];identities=set()
    if draws<256:raise ValueError('At least 256 independent replay draws required')
    for case in cases:
        gid=str(case['game_id']);identity=(gid,case['platform'])
        if identity in identities:raise ValueError('Duplicate replay game')
        identities.add(identity)
        kickoff=pd.Timestamp(case['kickoff']);frozen=pd.Timestamp(case['frozen_at'])
        if kickoff.tzinfo is None or frozen.tzinfo is None or frozen>=kickoff:
            raise ValueError('Frozen pregame inputs must precede timezone-aware kickoff')
        dates.append(kickoff.tz_convert('UTC'))
        pool=pd.DataFrame(case['pool']);roles=apply_player_profiles(case['roles'],players)
        if pool.Name.duplicated().any() or len(pool.Team.unique())!=2:
            raise ValueError('Replay needs unique players from exactly two teams')
        teams=set(pool.Team.astype(str))
        if set(pool.Opponent.astype(str))!=teams:raise ValueError('Replay opponent mismatch')
        seed_for_game=seed+int(sha256(gid.encode()).hexdigest()[:8],16)
        effective=dict(case.get('incumbent_parameters',{}),**(parameters or {}))
        fitted_inputs=case['projection_inputs'];gains=case['market_gain']
        if parameters is not None:
            from simmah_projection_inputs import fit_projection_inputs
            from simmah_market_calibration import calibrate_market_inputs
            from simmah_nfl_scoring import score_nfl_stat_line
            settings=case['fit_settings']
            fitted_inputs,_=fit_projection_inputs(pool,roles,case['platform'],score_nfl_stat_line,
                pilot_n=int(settings['pilot_n']),iterations=int(settings['iterations']),learned_parameters=effective)
            gains,_=calibrate_market_inputs(pool,roles,fitted_inputs,case['weather'],case['platform'],
                case['market_targets'],pilot_n=max(512,int(settings['pilot_n'])),learned_parameters=effective)
        stats=simulate_stat_lines(pool,roles,np.random.default_rng(seed_for_game),draws,
            correlation_strength=float(case.get('correlation_strength',1.)),
            weather_by_team=case['weather'],projection_inputs=fitted_inputs,
            market_gain=gains,scoring_platform=case['platform'],learned_parameters=effective)
        vectors=[];truth=[]
        for row in pool.itertuples():
            actual=case['actual_stats'][row.Name]
            if set(actual)!=set(STAT_KEYS):raise ValueError('Complete explicit raw stat actuals required, including zeros')
            for stat in STAT_KEYS:
                value=float(actual[stat]);sample=np.asarray(stats[row.Name][stat],float)
                if not np.isfinite(value) or not np.isfinite(sample).all():raise ValueError('Nonfinite replay outcomes')
                scale=(100. if stat.endswith('_yards') or stat in {'points_allowed','yards_allowed'}
                       else 10. if stat in {'passing_attempts','completions','rushing_attempts','targets','receptions'} else 1.)
                sample=sample/scale;value/=scale
                ordered=np.sort(sample);weights=(2*np.arange(draws)-draws+1)/(draws*draws)
                crps=float(np.abs(sample-value).mean()-np.dot(weights,ordered))
                mse=float((sample.mean()-value)**2)
                # Spread-sensitive proper score; floor handles deterministic zeros.
                variance=max(float(sample.var()),.01)
                nll=float(.5*(np.log(variance)+(value-sample.mean())**2/variance))
                key=str(row.Position)+'/'+stat
                bucket=metrics.setdefault(key,{'mean':[],'distribution':[],'variance':[]})
                bucket['mean'].append(mse);bucket['distribution'].append(crps);bucket['variance'].append(nll)
                vectors.append(sample);truth.append(value)
        matrix=np.asarray(vectors).T;target=np.asarray(truth)
        # Independent halves estimate E||X-X'||. This evaluates the joint
        # distribution, including cross-player dependence from the game ledger.
        half=draws//2
        energy=float(np.linalg.norm(matrix-target,axis=1).mean()-.5*np.linalg.norm(matrix[:half]-matrix[half:2*half],axis=1).mean())
        from simmah_nfl_scoring import score_nfl_stat_line
        score_samples=[];score_actual=[]
        for row in pool.itertuples():
            defense=int(str(row.Position).upper() in {'DST','D','DEF'})
            score_samples.append(score_nfl_stat_line(dict(stats[row.Name],is_defense=defense),case['platform'])/20.)
            score_actual.append(float(score_nfl_stat_line(dict(case['actual_stats'][row.Name],is_defense=defense),case['platform']))/20.)
        score_samples=np.asarray(score_samples).T;score_actual=np.asarray(score_actual)
        pair_loss=[]
        for i in range(len(score_actual)):
            for j in range(i):
                predicted=np.sqrt(np.abs(score_samples[:,i]-score_samples[:,j])).mean()
                observed=np.sqrt(abs(score_actual[i]-score_actual[j]))
                pair_loss.append(float((predicted-observed)**2))
        joint=metrics.setdefault('joint',{'correlations':[],'joint_distribution':[]})
        joint['correlations'].append(float(np.mean(pair_loss)))
        joint['joint_distribution'].append(energy)
    return {key:{loss:float(np.mean(values)) for loss,values in group.items()} for key,group in metrics.items()},dates


def validate_and_promote(candidate,cases,root=ROOT,*,draws=1024,min_games=20):
    if len({str(c['game_id']) for c in cases})<min_games:
        raise ValueError('At least '+str(min_games)+' distinct full-game replays required')
    if {c['platform'] for c in cases}!={'DraftKings','FanDuel'}:
        raise ValueError('Full-engine validation requires both DK and FD scoring contexts')
    positions={str(row['Position']) for case in cases for row in case['pool']}
    if not {'QB','RB','WR','TE','K'}<=positions or not positions&{'DST','D','DEF'}:
        raise ValueError('Validation must cover QB, RB, WR, TE, K and DST')
    validate_parameters(candidate['parameters'])
    incumbent_versions={case.get('incumbent_version') for case in cases}
    if len(incumbent_versions)!=1:raise ValueError('Promotion replays must use one incumbent version')
    parameters=dict(cases[0].get('incumbent_parameters',{}),**candidate['parameters'])
    baseline,dates=replay_losses(cases,None, {},draws=draws)
    if min(dates).date().isoformat()<=candidate['validation_through']:
        raise ValueError('Promotion games must follow ALL training and event-selection games')
    if any(str(case['game_id']) in candidate.get('source_game_ids',[]) for case in cases):
        raise ValueError('Archive/promotion game overlap')
    tested,_=replay_losses(cases,parameters,candidate['players'],draws=draws)
    # Require all position/stat objectives not to regress, and a material joint
    # improvement. No quiet averaging over a regression in another category.
    comparisons={key:{loss:{'baseline':old,'candidate':tested[key][loss],
        'passed':bool(tested[key][loss]<=old+1e-9)} for loss,old in group.items()} for key,group in baseline.items()}
    no_regression=all(item['passed'] for group in comparisons.values() for item in group.values())
    joint=baseline['joint']['correlations'];joint_new=tested['joint']['correlations']
    accepted=no_regression and joint_new<joint*.995
    report=dict(candidate,parameters=parameters,status='accepted' if accepted else 'rejected full-engine replay',
        replay_games=len(cases),replay_game_ids=[str(case['game_id']) for case in cases],
        replay_inputs_sha256=digest(cases),engine_sha256=engine_digest(),draws=draws,
        validation_through=max(dates).date().isoformat(),replay_metrics=comparisons,
        minimum_joint_improvement=.005)
    report['version']=digest(report)[:16]
    root=Path(root);atomic_json(root/'trials'/(report['version']+'.json'),report)
    if accepted:
        index_path=root/'index.json'
        index=json.loads(index_path.read_text()) if index_path.exists() else {'schema':SCHEMA,'versions':[]}
        # Existing accepted incumbent comparison is required before replacement.
        # This first implementation never silently replaces a validated model.
        if index['versions']:
            incumbent=model_for_date(min(dates).date().isoformat(),root)
            if incumbent is None or any(case.get('incumbent_version')!=incumbent['version'] for case in cases):
                raise ValueError('Replays must freeze the active incumbent model before replacing it')
        filename=report['version']+'.json';atomic_json(root/'versions'/filename,report)
        index['versions'].append({'file':filename,'validation_through':report['validation_through'],'sha256':digest(report)})
        atomic_json(index_path,index)
    return report


def capture_pregame_inputs(pool,roles,platform,parameters,weather,market_gain,game_starts,cache_root,now=None,incumbent=None,fit_settings=None,market_targets=None,correlation_strength=1.):
    """Private dated per-game snapshots; never publish user slate inputs to Git."""
    now=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    if now.tzinfo is None:raise ValueError('Capture requires timezone-aware clock')
    snapshots=[];seen=set()
    for row in pool.itertuples():
        teams=tuple(sorted((str(row.Team),str(row.Opponent))))
        if teams in seen or not set(teams)<=set(pool.Team.astype(str)):continue
        seen.add(teams);times=[]
        for team in teams:
            raw=game_starts.get(team)
            if raw is None:break
            stamp=pd.Timestamp(raw)
            if pd.isna(stamp):break
            if stamp.tzinfo is None:stamp=stamp.tz_localize('America/New_York')
            times.append(stamp.tz_convert('UTC'))
        if len(times)!=2 or times[0]!=times[1] or times[0]<=now:continue
        players=pool.loc[pool.Team.astype(str).isin(teams)].copy();names=set(players.Name)
        case={'schema':SCHEMA,'game_id':times[0].date().isoformat()+'-'+'-'.join(teams),
              'kickoff':times[0].isoformat(),'frozen_at':now.isoformat(),'platform':platform,
              'correlation_strength':float(correlation_strength),
              'incumbent_version':incumbent['version'] if incumbent else None,
              'incumbent_parameters':incumbent['parameters'] if incumbent else {},
              'pool':players.to_dict('records'),'roles':{name:value for name,value in roles.items() if name in names},
              'fit_settings':fit_settings or {'pilot_n':1024,'iterations':8},
              'market_targets':{team:value for team,value in (market_targets or {}).items() if team in teams},
              'projection_inputs':{name:value for name,value in parameters.items() if name in names},
              'weather':{team:weather.get(team,{}) for team in teams},
              'market_gain':{team:market_gain.get(team,1.) for team in teams},
              'status':'pregame inputs only; explicit final raw actuals required'}
        identity=digest(case);path=Path(cache_root)/'replay_inputs'/(identity+'.json')
        atomic_json(path,case);snapshots.append(str(path))
    return snapshots


def slate_clock_inputs(pool):
    """Only confirmed dated kickoff columns; missing clocks never mean 'today'."""
    starts={}
    for team,rows in pool.groupby('Team'):
        for column in ('Game Start','Weather Kickoff'):
            if column not in rows:continue
            values=[]
            for raw in rows[column]:
                try:
                    stamp=pd.Timestamp(raw)
                    if pd.isna(stamp):continue
                    if stamp.tzinfo is None:stamp=stamp.tz_localize('America/New_York')
                    values.append(stamp.tz_convert('UTC'))
                except (TypeError,ValueError):continue
            if len(values)==len(rows) and len(set(values))==1:
                starts[str(team)]=values[0].isoformat();break
    if len(starts)!=pool.Team.nunique():
        # Dated native salary fields can establish a slate day even when no
        # verified kickoff clock was recovered. They never fabricate a clock.
        import re
        days=[]
        for row in pool.to_dict('records'):
            found=[]
            for column in ('Game Info','Game','Start Time'):
                text=str(row.get(column,''))
                match=re.search(r'(?<![0-9])(20[0-9]{2}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/20[0-9]{2})(?![0-9])',text)
                if match:
                    try:found.append(pd.Timestamp(match.group()).date().isoformat())
                    except ValueError:pass
            if not found or len(set(found))!=1:return None,{}
            days.append(found[0])
        return (min(days),{}) if days else (None,{})
    day=min(pd.Timestamp(value) for value in starts.values()).tz_convert('America/New_York').date().isoformat()
    return day,starts


def fit_joint_replay_candidate(candidate,cases,*,draws=512,min_games=20):
    """Fit volume dispersion and game dependence using earlier frozen games.

    These fitting games become part of candidate selection, so promotion must
    use another later set. No validation metric is reused as a training target.
    """
    if len({str(c['game_id']) for c in cases})<min_games:raise ValueError('Insufficient joint-training games')
    cutoff=max(pd.Timestamp(c['kickoff']) for c in cases).date().isoformat()
    if min(pd.Timestamp(c['kickoff']) for c in cases).date().isoformat()<=candidate['validation_through']:
        raise ValueError('Joint-training replays must follow archive selection games')
    parameters=dict(candidate['parameters'])
    def loss(settings):
        report,_=replay_losses(cases,settings,candidate['players'],draws=draws)
        return sum(value for group in report.values() for name,value in group.items() if name!='variance')
    best=loss(parameters);fits=[]
    for name,grid in {'pace_sd':[.04,.09,.15], 'environment_sd':[.04,.1,.18],
                      'opportunity_concentration':[0.,20.,80.,160.]}.items():
        chosen=parameters.get(name,DEFAULTS[name])
        for value in grid:
            trial=dict(parameters,**{name:value});score=loss(trial)
            if score<best:best=score;chosen=value
        parameters[name]=chosen;fits.append({'parameter':name,'value':chosen,'training_loss':best})
    result=dict(candidate,parameters=parameters,joint_training=fits,joint_training_sha256=digest(cases),
                joint_training_games=len({c['game_id'] for c in cases}),validation_through=cutoff)
    result['source_game_ids']=sorted(set(candidate['source_game_ids'])|{str(c['game_id']) for c in cases})
    result['version']=digest(result)[:16]
    return result
