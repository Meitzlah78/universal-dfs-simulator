"""Experimental NumPy NBA possession core; not connected to live builds.

Callers must supply calibrated event rates and on-court rotations. No normal
fantasy-point draws are used. Quarter boundaries are respected. Overtime requires explicit five-player
rotations; ties beyond the supplied overtime periods remain marked unresolved.
"""
from dataclasses import dataclass
import numpy as np
from simmah_nba_scoring import score_nba

STAT_NAMES=('FGM','3PM','FTM','REB','AST','STL','BLK','TO')

@dataclass(frozen=True)
class EventRates:
    turnover:float
    free_throw_trip:float
    three_share:float
    make_two:float
    make_three:float
    make_free_throw:float
    assisted:float
    offensive_rebound:float
    steal_on_turnover:float
    block_on_miss:float
    seconds_per_action:float

    def validate(self):
        for name,value in vars(self).items():
            if not np.isfinite(value) or (value<=0 if name=='seconds_per_action' else not 0<=value<=1):
                raise ValueError('Invalid NBA event rate: '+name)
        if self.turnover+self.free_throw_trip>1:
            raise ValueError('Turnover and free throw probabilities exceed one')


def simulate_game(rotations, profiles, rates, seed, overtime_rotations=None, platform='FanDuel'):
    """Simulate regulation from a fixed, explicit rotation per scenario.

    rotations: integer (scenarios, 2 teams, 48 minutes, 5 players), global player
    indices. profiles: (2 teams, players per team, 5 role weights), roles ordered
    shooter, assist, rebound, steal, block. Team rosters occupy disjoint index
    ranges. These are role weights, not supplied fantasy projections.
    """
    rotation=np.asarray(rotations)
    weights=np.asarray(profiles,float)
    if weights.ndim!=3 or weights.shape[0]!=2 or weights.shape[2]!=5 or (weights<0).any() or not np.isfinite(weights).all():
        raise ValueError('Finite nonnegative two-team role profiles required')
    size=weights.shape[1]
    if rotation.ndim!=4 or rotation.shape[1:]!=(2,48,5) or rotation.dtype.kind not in 'iu':
        raise ValueError('Explicit five-player rotations for 48 minutes required')
    if size<5 or not len(rotation):raise ValueError('At least five players per team and one scenario required')
    for team in (0,1):
        selected=rotation[:,team]
        if (selected<team*size).any() or (selected>=(team+1)*size).any() or np.any(np.diff(np.sort(selected,axis=-1),axis=-1)==0):
            raise ValueError('Rotation has wrong-team or duplicate on-court players')
    if len(rates)!=2:raise ValueError('One event-rate model per team required')
    for r in rates:r.validate()
    n=len(rotation)
    overtime=None if overtime_rotations is None else np.asarray(overtime_rotations)
    if overtime is not None:
        if overtime.ndim!=5 or overtime.shape[:2]!=(n,2) or overtime.shape[3:]!=(5,5) or overtime.dtype.kind not in 'iu':
            raise ValueError('Overtime rotations must be scenarios x teams x periods x 5 minutes x 5 players')
        for team in (0,1):
            selected=overtime[:,team]
            if (selected<team*size).any() or (selected>=(team+1)*size).any() or np.any(np.diff(np.sort(selected,axis=-1),axis=-1)==0):
                raise ValueError('Overtime rotation has wrong-team or duplicate players')
    rng=np.random.default_rng(seed)
    stats=np.zeros((n,2*size,len(STAT_NAMES)),np.int32)
    team_points=np.zeros((n,2),np.int32)
    clock=np.full(n,2880.);side=rng.integers(0,2,n)
    opening=side.copy();elapsed=np.zeros(n);period_clock=np.full(n,720.)
    quarter=np.ones(n,int);overtime_count=np.zeros(n,int)
    counters={k:np.zeros(n,np.int32) for k in ['field_goal_makes','field_goal_misses','free_throw_misses','credited_rebounds','credited_assists','turnovers','steals','blocks']}
    flat_weights=weights.reshape(2*size,5)
    def pick(ids,lineups,role,exclude=None):
        w=flat_weights[lineups,role]
        if exclude is not None:w[lineups==exclude[:,None]]=0
        # Uniform role allocation among eligible on-court players if all supplied
        # weights are zero; a scorer is still never his own assister.
        empty=w.sum(axis=1)<=0
        if empty.any():w[empty]=1 if exclude is None else (lineups[empty]!=exclude[empty,None])
        cdf=np.cumsum(w,axis=1);draw=rng.random(len(ids))*cdf[:,-1]
        return lineups[np.arange(len(ids)),np.minimum((cdf<draw[:,None]).sum(axis=1),4)]
    # Event subsets contain unique scenario IDs; no index pair repeats.
    # Buffered indexed addition is equivalent to add.at without its reduction cost.
    def add(ids,player,stat):stats[ids,player,STAT_NAMES.index(stat)]+=1
    actions=0
    while np.any(clock>0):
        actions+=1
        if actions>5000*(1+(overtime.shape[2] if overtime is not None else 0)):raise RuntimeError('NBA event simulation exceeded its bounded action limit')
        live=np.flatnonzero(clock>0)
        action_side=side.copy()
        for team in (0,1):
            ids=live[action_side[live]==team]
            if not len(ids):continue
            r=rates[team]
            duration=rng.gamma(4,r.seconds_per_action/4,len(ids))
            remaining=np.minimum(clock[ids],period_clock[ids])
            valid=duration<remaining
            consumed=np.minimum(duration,remaining)
            clock[ids]=np.maximum(0,clock[ids]-consumed)
            period_clock[ids]=np.maximum(0,period_clock[ids]-consumed)
            elapsed[ids]+=consumed
            ids=ids[valid]
            if not len(ids):continue
            minute=np.minimum((elapsed[ids]/60).astype(int),47)
            offense=rotation[ids,team,minute];defense=rotation[ids,1-team,minute]
            in_ot=overtime_count[ids]>0
            if in_ot.any():
                oi=ids[in_ot];op=overtime_count[oi]-1
                om=np.clip(((elapsed[oi]-2880-op*300)/60).astype(int),0,4)
                offense[in_ot]=overtime[oi,team,op,om]
                defense[in_ot]=overtime[oi,1-team,op,om]
            shooter=pick(ids,offense,0)
            choice=rng.random(len(ids))
            turn=choice<r.turnover
            trips=(choice>=r.turnover)&(choice<r.turnover+r.free_throw_trip)
            shots=~(turn|trips)
            if turn.any():
                ti=ids[turn];add(ti,shooter[turn],'TO');counters['turnovers'][ti]+=1
                stolen=rng.random(len(ti))<r.steal_on_turnover
                if stolen.any():
                    si=ti[stolen];add(si,pick(si,defense[turn][stolen],3),'STL');counters['steals'][si]+=1
                side[ti]=1-team
            if trips.any():
                ti=ids[trips];tp=shooter[trips]
                made=rng.random((len(ti),2))<r.make_free_throw
                stats[ti,tp,2]+=made.sum(axis=1)
                team_points[ti,team]+=made.sum(axis=1)
                counters['free_throw_misses'][ti]+=(~made).sum(axis=1)
                # Only the final miss creates a live rebound opportunity.
                last_miss=~made[:,-1]
                side[ti]=1-team
                if last_miss.any():
                    ri=ti[last_miss];oreb=rng.random(len(ri))<r.offensive_rebound
                    lineup=np.where(oreb[:,None],offense[trips][last_miss],defense[trips][last_miss])
                    add(ri,pick(ri,lineup,2),'REB');counters['credited_rebounds'][ri]+=1
                    side[ri]=np.where(oreb,team,1-team)
            if shots.any():
                si=ids[shots];sp=shooter[shots]
                three=rng.random(len(si))<r.three_share
                made=rng.random(len(si))<np.where(three,r.make_three,r.make_two)
                if made.any():
                    mi=si[made];mp=sp[made]
                    add(mi,mp,'FGM');add(mi[three[made]],mp[three[made]],'3PM')
                    team_points[mi,team]+=2+three[made]
                    counters['field_goal_makes'][mi]+=1
                    assisted=rng.random(len(mi))<r.assisted
                    if assisted.any():
                        ai=mi[assisted];ap=pick(ai,offense[shots][made][assisted],1,mp[assisted])
                        add(ai,ap,'AST');counters['credited_assists'][ai]+=1
                    side[mi]=1-team
                if (~made).any():
                    ri=si[~made];counters['field_goal_misses'][ri]+=1
                    blocked=rng.random(len(ri))<r.block_on_miss
                    if blocked.any():
                        bi=ri[blocked];add(bi,pick(bi,defense[shots][~made][blocked],4),'BLK');counters['blocks'][bi]+=1
                    oreb=rng.random(len(ri))<r.offensive_rebound
                    lineup=np.where(oreb[:,None],offense[shots][~made],defense[shots][~made])
                    add(ri,pick(ri,lineup,2),'REB');counters['credited_rebounds'][ri]+=1
                    side[ri]=np.where(oreb,team,1-team)
        # A shot may not span a period boundary. Expired periods advance without
        # crediting an event; overtime requires an explicit on-court rotation.
        next_quarter=(period_clock<=0)&(clock>0)&(overtime_count==0)
        quarter[next_quarter]+=1
        period_clock[next_quarter]=720
        next_period=quarter[next_quarter]
        side[next_quarter]=np.where((next_period==2)|(next_period==3),1-opening[next_quarter],opening[next_quarter])
        tied=(clock<=0)&(team_points[:,0]==team_points[:,1])
        can_extend=tied & (overtime_count < (overtime.shape[2] if overtime is not None else 0))
        if can_extend.any():
            overtime_count[can_extend]+=1
            clock[can_extend]=300
            period_clock[can_extend]=300
            side[can_extend]=rng.integers(0,2,int(can_extend.sum()))
    fgm,threes,ftm,reb,ast,stl,blk,to=np.moveaxis(stats,2,0)
    scores=score_nba(platform,fgm=fgm,threes=threes,ftm=ftm,rebounds=reb,assists=ast,steals=stl,blocks=blk,turnovers=to)
    return {'scores':scores.astype(np.float32),'stats':stats,'team_points':team_points,
        'requires_overtime':team_points[:,0]==team_points[:,1], 'overtime_periods':overtime_count, 'elapsed_seconds':elapsed, 'counters':counters,
        'engine':'experimental-nba-possession-v2-explicit-overtime'}

