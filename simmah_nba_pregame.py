"""Experimental pregame adapter from complete provider rotations and historical roles."""
import numpy as np
from simmah_nba_projections import team_key
from simmah_nba_rotation_schedule import build_rotation
from simmah_nba_markets import simulate_market_game
from simmah_nba_engine import simulate_game
from simmah_nba_projection_anchor import fit_player_means

ROLE_COLUMNS=['Historical '+r+' Rate' for r in ('Shot','Assist','Rebound','Steal','Block')]


class PregameEngine:
    def __init__(self,pool,markets,rates,max_overtimes=4,platform='FanDuel'):
        if not isinstance(max_overtimes,int) or not 1<=max_overtimes<=10:raise ValueError("Explicit bounded overtime count required")
        self.platform=platform
        self.max_overtimes=max_overtimes
        self.pool=pool.reset_index(drop=True).copy();self.rates=rates
        rates.validate()
        if self.pool['Player ID'].duplicated().any():raise ValueError('Duplicate player IDs')
        required={'Projected Minutes',*ROLE_COLUMNS}
        if not required<=set(pool.columns):raise ValueError('Missing NBA projected minutes or historical role rates')
        self.games=[];covered=set()
        for market in markets:
            market=dict(market)
            market['teams']=tuple(market['teams'])
            market['implied_points']=tuple(market['implied_points'])
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
                active=group[np.isfinite(projection)&(projection>0)&~injured&(rotation_minutes!=0)]
                minutes=np.asarray(active['Projected Minutes'],float)
                roles=active[ROLE_COLUMNS].to_numpy(float)
                if len(active)<5 or not np.isfinite(minutes).all() or (minutes<=0).any() or (minutes>48).any():
                    invalid=~np.isfinite(minutes)|(minutes<=0)|(minutes>48)
                    labels=active.get('Name',active['Player ID']).astype(str)
                    detail=', '.join(labels.loc[invalid]) if invalid.any() else 'fewer than five rotation players'
                    raise ValueError('Complete positive projected rotation required for '+team+': '+detail)
                if abs(minutes.sum()-240)>1e-6:
                    raise ValueError(f'{team} projected rotation totals {minutes.sum():.1f} minutes; 240 required')
                missing=~np.isfinite(roles).all(axis=1)|(roles<0).any(axis=1)
                if missing.any():
                    names=active.loc[missing,'Name'] if 'Name' in active else active.loc[missing,'Player ID']
                    raise ValueError('Missing historical player roles for '+team+': '+', '.join(names.astype(str)))
                if (roles.sum(axis=0)<=0).any():
                    raise ValueError('Unsupported historical role totals for '+team)
                groups.append((active.index.to_numpy(),minutes,roles))
            covered.update(pair);self.games.append((market,groups))
        if covered!=set(self.pool['Team'].map(team_key)):
            raise ValueError('Every uploaded NBA game needs complete market lines')
        self.last_report=[]
        self.prepared={}

    def __call__(self,n,seed):
        if not isinstance(n,int) or n<1:raise ValueError('Positive simulation count required')
        output=np.zeros((n,len(self.pool)),np.float32);reports=[]
        for game_index,(market,groups) in enumerate(self.games):
            size=max(len(g[0]) for g in groups);profiles=np.zeros((2,size,5));rotations=[];overtime=[]
            for team,(ids,minutes,roles) in enumerate(groups):
                padded=np.zeros(size);padded[:len(ids)]=minutes
                profiles[team,:len(ids)]=roles
                overtime.append(np.stack([build_rotation(np.tile(padded*5/48,(n,1)),seed+game_index*97+team+10000+ot*11,team*size,period_minutes=5) for ot in range(self.max_overtimes)],axis=1))
                rotations.append(build_rotation(np.tile(padded,(n,1)),seed+game_index*97+team,team*size))
            rotation=np.stack(rotations,axis=1);ot=np.stack(overtime,axis=1)
            targets=np.zeros((2,size))
            for team,(ids,_,_) in enumerate(groups):
                targets[team,:len(ids)]=self.pool.loc[ids,'Projection'].to_numpy(float)
            if game_index not in self.prepared:
                pilot=min(n,1024);fit_seed=71333+game_index*97
                baseline=simulate_market_game(rotation[:pilot],profiles,[self.rates]*2,
                    market['implied_points'],fit_seed,overtime_rotations=ot[:pilot],platform=self.platform)
                fitted_profiles,fitted_rates,anchor=fit_player_means(rotation[:pilot],profiles,
                    baseline['calibrated_rates'],targets,fit_seed+17,overtime_rotations=ot[:pilot],platform=self.platform)
                final=simulate_market_game(rotation[:pilot],fitted_profiles,fitted_rates,
                    market['implied_points'],fit_seed+31,overtime_rotations=ot[:pilot],platform=self.platform)
                self.prepared[game_index]=(fitted_profiles,final['calibrated_rates'],anchor,
                    baseline['market_calibration']['baseline_pilot_means'])
            fitted_profiles,fitted_rates,anchor,initial=self.prepared[game_index]
            result=simulate_game(rotation,fitted_profiles,fitted_rates,seed+game_index*97+3,
                                 overtime_rotations=ot,platform=self.platform)
            for team,(ids,_,_) in enumerate(groups):
                output[:,ids]=result['scores'][:,team*size:team*size+len(ids)]
            means=result['team_points'].mean(axis=0);target=np.asarray(market['implied_points'])
            calibration={'targets':target.tolist(),'baseline_pilot_means':initial,
                         'evaluation_means':means.tolist(),'residual':(means-target).tolist(),
                         'within_four_points':bool((abs(means-target)<=4).all()),
                         'status':'experimental cached event calibration; inspect residuals'}
            player_means=result['scores'].mean(axis=0,dtype=np.float64).reshape(2,size)
            active=targets>0;error=abs(player_means-targets)[active]
            reports.append({'teams':market['teams'],'calibration':calibration,
                            'player_anchor':anchor,
                            'evaluation_player_mean_mae':float(error.mean()),
                            'evaluation_player_mean_max_error':float(error.max()),
                            'overtime_fraction':float((result['overtime_periods']>0).mean()),
                            'max_overtimes_supplied':self.max_overtimes,
                            'unresolved_tie_fraction':float(result['requires_overtime'].mean())})
        self.last_report=reports
        return output
