"""Experimental pregame adapter from complete provider rotations and historical roles."""
import numpy as np
from simmah_nba_projections import team_key
from simmah_nba_rotation_schedule import build_rotation
from simmah_nba_markets import simulate_market_game
from simmah_nba_engine import simulate_game
from simmah_nba_projection_anchor import fit_player_means
from simmah_nba_minutes import allocate_minutes

ROLE_COLUMNS=['Historical '+r+' Rate' for r in ('Shot','Assist','Rebound','Steal','Block')]


def validate_game_reports(reports):
    """Reject unusable draws before candidate/field generation and scoring."""
    problems=[]
    for report in reports:
        game=' vs '.join(map(str,report['teams']))
        calibration=report['calibration']
        if calibration.get('applied',True) and not calibration.get('within_four_points'):
            problems.append(game+': simulation missed the market calibration check')
        if report['unresolved_tie_fraction']>0:
            problems.append(game+': simulation left unresolved overtime')
    if problems:raise ValueError('; '.join(problems))


class PregameEngine:
    def __init__(self,pool,markets,rates,max_overtimes=10,platform='FanDuel',require_markets=False,
                 parallel=True,game_index_offset=0):
        if not isinstance(max_overtimes,int) or not 1<=max_overtimes<=10:raise ValueError("Explicit bounded overtime count required")
        self.platform=platform
        self.parallel=parallel;self.game_index_offset=game_index_offset;self.progress=None
        if not isinstance(game_index_offset,int) or game_index_offset<0:raise ValueError('Invalid NBA game seed offset')
        self.max_overtimes=max_overtimes
        self.pool=pool.reset_index(drop=True).copy();self.rates=rates
        rates.validate()
        if self.pool['Player ID'].duplicated().any():raise ValueError('Duplicate player IDs')
        required={'Projected Minutes',*ROLE_COLUMNS}
        if not required<=set(pool.columns):raise ValueError('Missing NBA projected minutes or historical role rates')
        markets=[dict(m) for m in markets]
        uploaded={tuple(sorted((team_key(r.Team),team_key(r.Opponent)))) for r in self.pool.itertuples()}
        supplied={tuple(sorted(map(team_key,m['teams']))) for m in markets}
        if not supplied<=uploaded:raise ValueError('Market does not match uploaded game')
        priced={tuple(sorted(map(team_key,m['teams']))) for m in markets if m.get('implied_points') is not None}
        self.missing_markets=sorted(uploaded-priced)
        if require_markets and self.missing_markets:
            raise ValueError('Every uploaded NBA game needs complete market lines')
        markets.extend({'teams':pair,'implied_points':None,'source':'Unavailable'} for pair in sorted(uploaded-supplied))
        self.games=[];covered=set();problems=[];self.rotation_reconciliation=[]
        for market in markets:
            market=dict(market)
            market['teams']=tuple(market['teams'])
            market['implied_points']=tuple(market['implied_points']) if market.get('implied_points') is not None else None
            pair=tuple(map(team_key,market['teams']))
            if len(pair)!=2 or pair[0]==pair[1] or covered&set(pair):raise ValueError('Duplicate NBA market teams')
            groups=[]
            for team,opp in (pair,pair[::-1]):
                group=self.pool[self.pool['Team'].map(team_key)==team]
                if group.empty or set(group['Opponent'].map(team_key))!={opp}:
                    raise ValueError('Market does not match uploaded game')
                injured=group['Injury Status'].astype(str).str.upper().isin(['OUT','O','IR','SUSPENDED'])
                projection=np.asarray(group['Projection'],float)
                # Explicit provider zero-minute reserves cannot enter a rotation.
                # Unknown minutes remain in validation below and still block.
                rotation_minutes=np.asarray(group['Projected Minutes'],float)
                rotation_only=group['Rotation Only'].eq(True) if 'Rotation Only' in group else np.zeros(len(group),bool)
                active=group[((np.isfinite(projection)&(projection>0))|rotation_only)&~injured&(rotation_minutes!=0)]
                minutes=np.asarray(active['Projected Minutes'],float)
                roles=active[ROLE_COLUMNS].to_numpy(float)
                if len(active)<5 or not np.isfinite(minutes).all() or (minutes<=0).any() or (minutes>48).any():
                    invalid=~np.isfinite(minutes)|(minutes<=0)|(minutes>48)
                    labels=active.get('Name',active['Player ID']).astype(str)
                    detail=', '.join(labels.loc[invalid]) if invalid.any() else 'fewer than five rotation players'
                    problems.append('Complete positive projected rotation required for '+team+': '+detail)
                if np.isfinite(minutes).all() and abs(minutes.sum()-240)>1e-6:
                    # Provider minutes are estimates and may not add to a full
                    # game. Preserve source forecasts; only physical simulation
                    # shares are normalized. A complete provider budget can also
                    # retain stale minutes for a now-OUT player. In that bounded
                    # case the remaining known rotation absorbs those shares.
                    # Unknown healthy minutes and unexplained shortfalls block.
                    total=float(minutes.sum())
                    inactive_mask=injured.to_numpy() & (rotation_minutes>0)
                    inactive_minutes=float(rotation_minutes[inactive_mask].sum())
                    raw_total=float(rotation_minutes.sum())
                    injury_budget=(np.isfinite(rotation_minutes).all()
                        and (rotation_minutes>=0).all() and (rotation_minutes<=48).all()
                        and 192<=total<228 and 0<inactive_minutes<=48
                        and 228<=raw_total<=252
                        and abs(raw_total-total-inactive_minutes)<1e-6)
                    if (len(active)>=6 and (minutes>0).all() and (minutes<=48).all()
                            and (228<=total<=252 or injury_budget)):
                        adjusted=allocate_minutes(minutes[None,:])[0]
                        self.rotation_reconciliation.append({'team':team,'provider_total':total,
                            'simulation_total':float(adjusted.sum()),
                            'basis':'inactive-player budget reconciliation' if injury_budget else 'small provider budget discrepancy',
                            'provider_total_before_inactive_exclusions':raw_total,
                            'excluded_inactive_minutes':inactive_minutes,
                            'excluded_inactive_players':[{'id':str(row['Player ID']),
                                'name':str(row.get('Name',row['Player ID'])),
                                'provider_minutes':float(row['Projected Minutes'])}
                                for _,row in group.loc[inactive_mask].iterrows()],
                            'players':[{'id':str(pid),'provider_minutes':float(a),'simulation_minutes':float(b)}
                                for pid,a,b in zip(active['Player ID'],minutes,adjusted)]})
                        minutes=adjusted
                    else:
                        problems.append(f'{team} projected rotation totals {total:.1f} minutes; 240 required')
                missing=~np.isfinite(roles).all(axis=1)|(roles<0).any(axis=1)
                if missing.any():
                    names=active.loc[missing,'Name'] if 'Name' in active else active.loc[missing,'Player ID']
                    problems.append('Missing historical player roles for '+team+': '+', '.join(names.astype(str)))
                unsupported=np.isfinite(roles).all(axis=1)&(roles.sum(axis=1)<=0)
                if unsupported.any():
                    names=active.loc[unsupported,'Name'] if 'Name' in active else active.loc[unsupported,'Player ID']
                    problems.append('Positive projections need supported event roles for '+team+': '+', '.join(names.astype(str)))
                if (roles.sum(axis=0)<=0).any():
                    problems.append('Unsupported historical role totals for '+team)
                groups.append((active.index.to_numpy(),minutes,roles))
            covered.update(pair);self.games.append((market,groups))
        if problems:raise ValueError('; '.join(problems))
        if covered!=set(self.pool['Team'].map(team_key)):
            raise ValueError('Every uploaded NBA game needs complete market lines')
        self.last_report=[]
        self.prepared={}

    def set_progress(self,progress):self.progress=progress

    def __call__(self,n,seed):
        if not isinstance(n,int) or n<1:raise ValueError('Positive simulation count required')
        if self.parallel and len(self.games)>1 and n>=512:
            from simmah_nba_parallel import simulate_parallel,worker_count
            from concurrent.futures.process import BrokenProcessPool
            if worker_count()>1:
                try:return simulate_parallel(self,n,seed)
                except (OSError,BrokenProcessPool):
                    # Restricted hosts retain the same sequential engine.
                    self.parallel=False
        output=np.zeros((n,len(self.pool)),np.float32);reports=[]
        for local_index,(market,groups) in enumerate(self.games):
            game_index=local_index+self.game_index_offset
            size=max(len(g[0]) for g in groups);profiles=np.zeros((2,size,5));rotations=[];overtime=[]
            for team,(ids,minutes,roles) in enumerate(groups):
                padded=np.zeros(size);padded[:len(ids)]=minutes
                profiles[team,:len(ids)]=roles
                overtime.append(np.stack([build_rotation(np.tile(padded*5/48,(n,1)),seed+game_index*97+team+10000+ot*11,team*size,period_minutes=5) for ot in range(self.max_overtimes)],axis=1))
                rotations.append(build_rotation(np.tile(padded,(n,1)),seed+game_index*97+team,team*size))
            rotation=np.stack(rotations,axis=1);ot=np.stack(overtime,axis=1)
            targets=np.zeros((2,size))
            for team,(ids,_,_) in enumerate(groups):
                projected=self.pool.loc[ids,'Projection'].to_numpy(float)
                targets[team,:len(ids)]=np.where(np.isfinite(projected)&(projected>0),projected,0.)
            if game_index not in self.prepared:
                pilot=min(n,1024);fit_seed=71333+game_index*97
                if market['implied_points'] is None:
                    fitted_profiles,fitted_rates,anchor=fit_player_means(rotation[:pilot],profiles,
                        [self.rates]*2,targets,fit_seed+17,overtime_rotations=ot[:pilot],platform=self.platform)
                    self.prepared[game_index]=(fitted_profiles,fitted_rates,anchor,None)
                else:
                    baseline=simulate_market_game(rotation[:pilot],profiles,[self.rates]*2,
                        market['implied_points'],fit_seed,overtime_rotations=ot[:pilot],platform=self.platform,calibration_only=True)
                    fitted_profiles,fitted_rates,anchor=fit_player_means(rotation[:pilot],profiles,
                        baseline['calibrated_rates'],targets,fit_seed+17,overtime_rotations=ot[:pilot],platform=self.platform)
                    final=simulate_market_game(rotation[:pilot],fitted_profiles,fitted_rates,
                        market['implied_points'],fit_seed+31,overtime_rotations=ot[:pilot],platform=self.platform,calibration_only=True)
                    self.prepared[game_index]=(fitted_profiles,final['calibrated_rates'],anchor,
                        baseline['market_calibration']['baseline_pilot_means'])
            fitted_profiles,fitted_rates,anchor,initial=self.prepared[game_index]
            result=simulate_game(rotation,fitted_profiles,fitted_rates,seed+game_index*97+3,
                                 overtime_rotations=ot,platform=self.platform)
            for team,(ids,_,_) in enumerate(groups):
                output[:,ids]=result['scores'][:,team*size:team*size+len(ids)]
            means=result['team_points'].mean(axis=0)
            if market['implied_points'] is None:
                calibration={'applied':False,'targets':None,'baseline_pilot_means':None,
                    'evaluation_means':means.tolist(),'residual':None,'within_four_points':None,
                    'status':'Market unavailable; provider player targets anchored using historical event rates. No spread or total invented.'}
            else:
                target=np.asarray(market['implied_points'])
                calibration={'applied':True,'targets':target.tolist(),'baseline_pilot_means':initial,
                         'evaluation_means':means.tolist(),'residual':(means-target).tolist(),
                         'within_four_points':bool((abs(means-target)<=4).all()),
                         'status':'experimental cached event calibration; inspect residuals'}
            player_means=result['scores'].mean(axis=0,dtype=np.float64).reshape(2,size)
            active=targets>0;error=abs(player_means-targets)[active]
            reports.append({'teams':market['teams'],'calibration':calibration,
                            'player_anchor':anchor,
                            'evaluation_player_mean_mae':float(error.mean()),
                            'evaluation_player_mean_max_error':float(error.max()),
                            'blowout_rotation_fraction_by_team':result['blowout_rotation_applied'].mean(axis=0).tolist(),
                            'overtime_fraction':float((result['overtime_periods']>0).mean()),
                            'max_overtimes_supplied':self.max_overtimes,
                            'unresolved_tie_fraction':float(result['requires_overtime'].mean())})
        self.last_report=reports
        return output




