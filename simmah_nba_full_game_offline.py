"""Offline integrated NBA challenger. Never imported by production.

NumPy NBA possession core with experimental score-driven late rotations.

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


def _duplicate_court_players(selected):
    # Five fixed slots: pair comparisons avoid sorting/copying every court row.
    return any(np.any(selected[...,i]==selected[...,j])
               for i in range(5) for j in range(i+1,5))


def simulate_game(rotations, profiles, rates, seed, overtime_rotations=None, platform='FanDuel', *, shooting=None, target_minutes=None, foul_rates=None, blowout=False, clock_model=None, shot_hazards=None, possession_audit=False):
    """Simulate the supplied rotations without score-driven substitutions.

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
        if (selected<team*size).any() or (selected>=(team+1)*size).any() or _duplicate_court_players(selected):
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
            if (selected<team*size).any() or (selected>=(team+1)*size).any() or _duplicate_court_players(selected):
                raise ValueError('Overtime rotation has wrong-team or duplicate players')
    shooting=np.asarray(shooting,float)
    target_minutes=np.asarray(target_minutes,float)
    foul_rates=np.asarray(foul_rates,float)
    if shooting.shape!=(2*size,4) or not np.isfinite(shooting).all() or (shooting<0).any() or (shooting>1).any():
        raise ValueError('Explicit player shooting splits required')
    if target_minutes.shape!=(2,size) or not np.isfinite(target_minutes).all() or (target_minutes<0).any() or not np.allclose(target_minutes.sum(axis=1),240):
        raise ValueError('Complete target minute ledgers required')
    if foul_rates.shape!=(2*size,) or not np.isfinite(foul_rates).all() or (foul_rates<0).any():raise ValueError('Pregame foul intensities required')
    if clock_model is not None:
        p=float(clock_model.get('violation_probability',float('nan')))
        if not np.isfinite(p) or not 0<=p<=1:raise ValueError('Valid explicit shot-clock violation probability required')
    if shot_hazards is not None:
        one=float(shot_hazards['and_one_probability_per_make'])
        if not np.isfinite(one) or not 0<=one<=1:raise ValueError('Invalid and-one probability')
        for key in ['fg_rebound_outcomes','ft_rebound_outcomes']:
            value=np.asarray(shot_hazards[key],float)
            if value.shape!=(4,) or not np.isfinite(value).all() or (value<0).any() or not np.isclose(value.sum(),1.):raise ValueError('Invalid player/team rebound probabilities')
    rng=np.random.default_rng(seed)
    stats=np.zeros((n,2*size,len(STAT_NAMES)),np.int32)
    team_points=np.zeros((n,2),np.int32)
    clock=np.full(n,2880.);side=rng.integers(0,2,n)
    opening=side.copy();elapsed=np.zeros(n);period_clock=np.full(n,720.)
    quarter=np.ones(n,int);overtime_count=np.zeros(n,int)
    counters={k:np.zeros(n,np.int32) for k in ['field_goal_makes','field_goal_misses','free_throw_misses','credited_rebounds','credited_assists','turnovers','steals','blocks']}
    flat_weights=weights.reshape(2*size,5)
    def pick(ids,lineups,role,exclude=None):
        cdf=flat_weights[lineups,role]
        if exclude is not None:cdf[lineups==exclude[:,None]]=0
        # Uniform role allocation among eligible on-court players if all supplied
        # weights are zero; a scorer is still never his own assister.
        if len(ids)>=128:
            # Five columns only: explicit left-to-right sums avoid the generic
            # row-wise scan for large batches without changing addition order.
            cdf[:,1]+=cdf[:,0]
            cdf[:,2]+=cdf[:,1]
            cdf[:,3]+=cdf[:,2]
            cdf[:,4]+=cdf[:,3]
        else:
            np.cumsum(cdf,axis=1,out=cdf)
        empty=cdf[:,-1]<=0
        if empty.any():
            uniform=np.ones((int(empty.sum()),5)) if exclude is None else (lineups[empty]!=exclude[empty,None])
            cdf[empty]=np.cumsum(uniform,axis=1)
        draw=rng.random(len(ids))*cdf[:,-1]
        # Five on-court players: the final CDF entry is the draw's upper
        # bound. Compare the first four boundaries without a row reduction.
        pick_index=(cdf[:,0]<draw).astype(np.intp)
        pick_index+=(cdf[:,1]<draw)
        pick_index+=(cdf[:,2]<draw)
        pick_index+=(cdf[:,3]<draw)
        return lineups[np.arange(len(ids)),pick_index]
    # Event subsets contain unique scenario IDs; no index pair repeats.
    # Buffered indexed addition is equivalent to add.at without its reduction cost.
    def add(ids,player,stat):
        if np.any(personal[ids,player]>=6):raise RuntimeError('Disqualified player received a later on-court stat')
        stats[ids,player,STAT_NAMES.index(stat)]+=1
    personal=np.zeros((n,2*size),np.int16)
    player_seconds=np.zeros((n,2*size),float)
    dq_seconds=np.full((n,2*size),np.nan)
    shot_clock=np.full(n,24.)
    team_fouls=np.zeros((n,2),np.int16)
    attempts=np.zeros((n,2*size,3),np.int32) # FGA, 3PA, FTA
    extra={k:np.zeros(n,np.int32) for k in ['shot_clock_violations','one_shot_trips','two_shot_trips','three_shot_trips','technical_trips','nonshooting_fouls','offensive_rebounds']}
    from simmah_nba_clock_offline import BUCKETS,sample_duration
    origin=np.zeros(n,np.int8)
    clock_ledger=np.zeros((n,len(BUCKETS)))
    regulation_ledger=np.zeros_like(clock_ledger)
    action_counts=np.zeros_like(clock_ledger,dtype=np.int32)
    expiration_counts=np.zeros_like(clock_ledger,dtype=np.int32)
    clock_rng=np.random.default_rng(np.random.SeedSequence([seed,4099])) if clock_model is not None else None
    extra['shooting_fouls']=np.zeros(n,np.int32)
    extra['possession_changes']=np.zeros(n,np.int32)
    def court(ids,team,minute):
        lineup=rotation[ids,team,minute].copy()
        in_ot=overtime_count[ids]>0
        if in_ot.any():
            oi=ids[in_ot];op=overtime_count[oi]-1
            om=np.clip(((elapsed[oi]-2880-op*300)/60).astype(int),0,4)
            lineup[in_ot]=overtime[oi,team,op,om]
        # Replace all disqualified players immediately. Foul-trouble and blowout
        # are soft substitutions, never permission to reuse an ineligible player.
        base=team*size;available=target_minutes[team]>0
        priority=target_minutes[team][None,:]*60-player_seconds[ids,base:base+size]
        foul=personal[ids,base:base+size]
        q=np.minimum(4,quarter[ids])
        trouble=(foul>=q[:,None]+1)&(q[:,None]<4)
        if blowout:
            late=(overtime_count[ids]==0)&(clock[ids]<=360)&(np.abs(team_points[ids,0]-team_points[ids,1])>=20)
            trouble|=late[:,None]&(target_minutes[team][None,:]>=28)
        priority-=2880*trouble
        legal=available[None,:]&(foul<6)
        if (legal.sum(axis=1)<5).any():raise ValueError('Offline exhausted roster exception unsupported; fewer than five legal players')
        priority=np.where(legal,priority,-np.inf)
        for slot in range(5):
            local=lineup[:,slot]-base
            bad=(foul[np.arange(len(ids)),local]>=6)|trouble[np.arange(len(ids)),local]
            if not bad.any():continue
            candidates=priority.copy()
            candidates[np.arange(len(ids))[:,None],lineup-base]=-np.inf
            replacement=np.argmax(candidates,axis=1)
            possible=np.isfinite(candidates[np.arange(len(ids)),replacement])
            replace=bad&possible
            lineup[replace,slot]=base+replacement[replace]
            if np.any(personal[ids,lineup[:,slot]]>=6):raise ValueError('Disqualified player remains on court')
        return lineup
    def foul_player(ids,lineup):
        w=foul_rates[lineup];w=np.where(w.sum(axis=1,keepdims=True)>0,w,1.)
        c=np.cumsum(w,axis=1);u=rng.random(len(ids))*c[:,-1]
        who=lineup[np.arange(len(ids)),(c[:,:-1]<u[:,None]).sum(axis=1)]
        personal[ids,who]+=1
        six=personal[ids,who]==6
        dq_seconds[ids[six],who[six]]=elapsed[ids[six]]
        team_fouls[ids,(who//size)]+=1
    extra['non_andone_shooting_fouls']=np.zeros(n,np.int32)
    extra['and_one_fouls']=np.zeros(n,np.int32)
    for context in ['fg','ft']:
        for outcome in ['miss_rebound_opportunities','player_oreb','player_dreb','team_oreb','team_dreb']:
            extra[context+'_'+outcome]=np.zeros(n,np.int32)
    possession_origins=['dead_ball_inbound','after_andone_oreb','after_foul','after_ft','after_make','after_dreb','after_turnover','period_start']
    pos_start=np.zeros(n);pos_origin=np.full(n,7,int);pos_side=side.copy()
    pos_count=np.zeros((n,2),np.int32);pos_completed=np.zeros((n,8),np.int32);pos_seconds=np.zeros((n,8))
    pos_terminals=np.zeros((n,8),np.int32);pos_terminal_seconds=np.zeros((n,8))
    oreb_start_sum=np.zeros(n);oreb_pending=np.zeros(n,int);oreb_tail_count=np.zeros(n,np.int32);oreb_tail_seconds=np.zeros(n)
    made_action=np.zeros(n,bool);sample_trace=[]
    def finish_possession(ids,reason,completed=True):
        if not possession_audit or not len(ids):return
        keep=(pos_side[ids]>=0)&(elapsed[ids]-pos_start[ids]>1e-10)
        ids=ids[keep]
        if not len(ids):return
        duration=elapsed[ids]-pos_start[ids];codes=pos_origin[ids]
        pos_count[ids,pos_side[ids]]+=1
        if completed:pos_completed[ids,codes]+=1;pos_seconds[ids,codes]+=duration
        else:pos_terminals[ids,codes]+=1;pos_terminal_seconds[ids,codes]+=duration
        oreb_tail_count[ids]+=oreb_pending[ids];oreb_tail_seconds[ids]+=oreb_pending[ids]*elapsed[ids]-oreb_start_sum[ids]
        if 0 in ids:
            sample_trace.append({'scenario':0,'offense':int(pos_side[0]),'start_elapsed':float(pos_start[0]),'end_elapsed':float(elapsed[0]),'seconds':float(elapsed[0]-pos_start[0]),'origin':possession_origins[pos_origin[0]],'end_reason':reason,'completed':completed})
        pos_start[ids]=elapsed[ids];pos_origin[ids]=origin[ids];pos_side[ids]=side[ids]
        oreb_pending[ids]=0;oreb_start_sum[ids]=0
        if not completed:pos_side[ids]=-1
    extra['team_offensive_rebounds']=np.zeros(n,np.int32)
    extra['team_defensive_rebounds']=np.zeros(n,np.int32)
    def resolve_rebound(ids,off,defense,rate,context,team):
        u=rng.random(len(ids))
        if shot_hazards is None:
            oreb=u<rate;credited=np.ones(len(ids),bool);team_rebound=np.zeros(len(ids),bool)
        else:
            probability=np.asarray(shot_hazards[context+'_rebound_outcomes'],float)
            cdf=np.cumsum(probability);cdf[-1]=1.
            outcome=np.searchsorted(cdf,u,side='right')
            oreb=(outcome==0)|(outcome==2);credited=outcome<2;team_rebound=~credited
            extra['team_offensive_rebounds'][ids]+=outcome==2
            extra['team_defensive_rebounds'][ids]+=outcome==3
        extra[context+'_miss_rebound_opportunities'][ids]+=1
        extra[context+'_player_oreb'][ids]+=oreb&credited
        extra[context+'_player_dreb'][ids]+=(~oreb)&credited
        extra[context+'_team_oreb'][ids]+=oreb&team_rebound
        extra[context+'_team_dreb'][ids]+=(~oreb)&team_rebound
        if possession_audit:
            continuing=oreb&credited&~made_action[ids]
            oi=ids[continuing];oreb_pending[oi]+=1;oreb_start_sum[oi]+=elapsed[oi]
        extra['offensive_rebounds'][ids]+=oreb&credited
        if credited.any():
            ri=ids[credited];lineup=np.where(oreb[credited,None],off[credited],defense[credited])
            add(ri,pick(ri,lineup,2),'REB');counters['credited_rebounds'][ri]+=1
        side[ids]=np.where(oreb,team,1-team);shot_clock[ids]=np.where(oreb,14.,24.)
        origin[ids]=np.where(team_rebound,0,np.where(oreb,1,5))
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
            made_action[ids]=False
            minute=np.minimum((elapsed[ids]/60).astype(int),47)
            full_offense=court(ids,team,minute);full_defense=court(ids,1-team,minute)
            previous_origin=origin[ids].copy()
            previous_ot=overtime_count[ids].copy()
            duration=rng.gamma(4,r.seconds_per_action/4,len(ids))
            planned_choice=None
            forced_violation=None
            if clock_model is not None:
                planned_choice=clock_rng.random(len(ids))
                duration=sample_duration(duration,r.seconds_per_action/4,previous_origin,shot_clock[ids],clock_model)
                technical_planned=(planned_choice>=r.turnover+r.free_throw_trip+.055)&(planned_choice<r.turnover+r.free_throw_trip+.057)
                duration[technical_planned]=0.
                forced_violation=(clock_rng.random(len(ids))<clock_model['violation_probability'])&~technical_planned
                duration[forced_violation]=shot_clock[ids[forced_violation]]
            remaining=np.minimum(clock[ids],period_clock[ids])
            violation=(duration>=shot_clock[ids])&(shot_clock[ids]<remaining)
            valid=(duration<remaining)&~violation
            consumed=np.minimum(np.minimum(duration,remaining),shot_clock[ids])
            clock_ledger[ids,previous_origin]+=consumed
            action_counts[ids,previous_origin]+=1
            reg=previous_ot==0
            regulation_ledger[ids[reg],previous_origin[reg]]+=consumed[reg]
            expiration_counts[ids[violation],previous_origin[violation]]+=1
            for line in (full_offense,full_defense):
                player_seconds[ids[:,None],line]+=consumed[:,None]
            shot_clock[ids]-=consumed
            if violation.any():
                vi=ids[violation];extra['shot_clock_violations'][vi]+=1
                side[vi]=1-team;shot_clock[vi]=24.;origin[vi]=6;extra['possession_changes'][vi]+=1
            clock[ids]=np.maximum(0,clock[ids]-consumed)
            period_clock[ids]=np.maximum(0,period_clock[ids]-consumed)
            elapsed[ids]+=consumed
            finish_possession(ids[violation],'shot_clock_turnover')
            ids=ids[valid]
            if not len(ids):continue
            offense=full_offense[valid];defense=full_defense[valid]
            shooter=pick(ids,offense,0)
            choice=rng.random(len(ids)) if planned_choice is None else planned_choice[valid]
            turn=choice<r.turnover
            trips=(choice>=r.turnover)&(choice<r.turnover+r.free_throw_trip)
            nonshoot=(choice>=r.turnover+r.free_throw_trip)&(choice<r.turnover+r.free_throw_trip+.055)
            technical=(choice>=r.turnover+r.free_throw_trip+.055)&(choice<r.turnover+r.free_throw_trip+.057)
            shots=~(turn|trips|nonshoot|technical)
            if nonshoot.any():
                ni=ids[nonshoot];foul_player(ni,defense[nonshoot]);extra['nonshooting_fouls'][ni]+=1;origin[ni]=2
                # Quarter bonus approximation; final-two-minute exception is not
                # yet modeled. Keep explicit in replay limitations.
                bonus=team_fouls[ni,1-team]>=5
                if bonus.any():trips[np.flatnonzero(nonshoot)[bonus]]=True
                defense[nonshoot]=court(ni,1-team,np.minimum((elapsed[ni]/60).astype(int),47))
                shot_clock[ni]=np.maximum(shot_clock[ni],14.)
            if technical.any():
                ti=ids[technical];tp=shooter[technical]
                made=rng.random(len(ti))<shooting[tp,3]
                stats[ti,tp,2]+=made;attempts[ti,tp,2]+=1;team_points[ti,team]+=made
                extra['technical_trips'][ti]+=1;extra['one_shot_trips'][ti]+=1
            shot_clock[ids[turn]]=24.
            if turn.any():
                ti=ids[turn];add(ti,shooter[turn],'TO');counters['turnovers'][ti]+=1
                stolen=rng.random(len(ti))<r.steal_on_turnover
                if stolen.any():
                    si=ti[stolen];add(si,pick(si,defense[np.flatnonzero(turn)[stolen]],3),'STL');counters['steals'][si]+=1
                side[ti]=1-team;origin[ti]=6
            if trips.any():
                ti=ids[trips];tp=shooter[trips]
                shooting_trip=~nonshoot[trips]
                if shooting_trip.any():
                    extra['shooting_fouls'][ti[shooting_trip]]+=1;extra['non_andone_shooting_fouls'][ti[shooting_trip]]+=1
                    fi=ti[shooting_trip];foul_player(fi,defense[np.flatnonzero(trips)[shooting_trip]])
                    defense[np.flatnonzero(trips)[shooting_trip]]=court(fi,1-team,np.minimum((elapsed[fi]/60).astype(int),47))
                count=np.where(shooting_trip&(rng.random(len(ti))<.04557),3,2)
                active_ft=np.arange(3)[None,:]<count[:,None]
                made=(rng.random((len(ti),3))<shooting[tp,3,None])&active_ft
                made_count=made.sum(axis=1)
                attempts[ti,tp,2]+=count
                extra['two_shot_trips'][ti[count==2]]+=1;extra['three_shot_trips'][ti[count==3]]+=1
                stats[ti,tp,2]+=made_count
                team_points[ti,team]+=made_count
                counters['free_throw_misses'][ti]+=count-made_count
                # Only the final miss creates a live rebound opportunity.
                last_miss=~made[np.arange(len(ti)),count-1]
                side[ti]=1-team;shot_clock[ti]=24.;origin[ti]=3
                if last_miss.any():
                    ri=ti[last_miss];rows=np.flatnonzero(trips)[last_miss]
                    resolve_rebound(ri,offense[rows],defense[rows],r.offensive_rebound,'ft',team)
            if shots.any():
                shot_rows=np.flatnonzero(shots)
                si=ids[shots];sp=shooter[shots]
                three=rng.random(len(si))<shooting[sp,0]
                # Team market calibration adjusts player efficiencies relative
                # to the unchanged pooled baseline; no fantasy scalar applied.
                probability=np.where(three,shooting[sp,2]*r.make_three/.37816492450638794,shooting[sp,1]*r.make_two/.5583666933546837)
                made=rng.random(len(si))<np.clip(probability,.01,.99)
                attempts[si,sp,0]+=1;attempts[si[three],sp[three],1]+=1
                if made.any():
                    mi=si[made];mp=sp[made];made_action[mi]=True
                    add(mi,mp,'FGM');add(mi[three[made]],mp[three[made]],'3PM')
                    team_points[mi,team]+=2+three[made]
                    counters['field_goal_makes'][mi]+=1
                    assisted=rng.random(len(mi))<r.assisted
                    if assisted.any():
                        ai=mi[assisted];ap=pick(ai,offense[shot_rows[made][assisted]],1,mp[assisted])
                        add(ai,ap,'AST');counters['credited_assists'][ai]+=1
                    side[mi]=1-team;shot_clock[mi]=24.;origin[mi]=4
                    andone=rng.random(len(mi))<(.03 if shot_hazards is None else shot_hazards['and_one_probability_per_make'])
                    if andone.any():
                        ai=mi[andone];ap=mp[andone];rows=shot_rows[made][andone]
                        foul_player(ai,defense[rows]);defense[rows]=court(ai,1-team,np.minimum((elapsed[ai]/60).astype(int),47));good=rng.random(len(ai))<shooting[ap,3]
                        stats[ai,ap,2]+=good;attempts[ai,ap,2]+=1;team_points[ai,team]+=good
                        extra['one_shot_trips'][ai]+=1;extra['shooting_fouls'][ai]+=1;extra['and_one_fouls'][ai]+=1;origin[ai]=3
                        miss=~good
                        if miss.any():
                            ri=ai[miss];counters['free_throw_misses'][ri]+=1
                            resolve_rebound(ri,offense[rows[miss]],defense[rows[miss]],r.offensive_rebound,'ft',team)
                if (~made).any():
                    ri=si[~made];counters['field_goal_misses'][ri]+=1
                    blocked=rng.random(len(ri))<r.block_on_miss
                    if blocked.any():
                        bi=ri[blocked];add(bi,pick(bi,defense[shot_rows[~made][blocked]],4),'BLK');counters['blocks'][bi]+=1
                    rows=shot_rows[~made]
                    resolve_rebound(ri,offense[rows],defense[rows],r.offensive_rebound,'fg',team)
            extra['possession_changes'][ids]+=(side[ids]!=team)
            finish_possession(ids[(side[ids]!=team)|made_action[ids]],'scoring_or_control_end')
        # A shot may not span a period boundary. Expired periods advance without
        # crediting an event; overtime requires an explicit on-court rotation.
        finish_possession(np.flatnonzero((period_clock<=0)|(clock<=0)),'period_end',False)
        next_quarter=(period_clock<=0)&(clock>0)&(overtime_count==0)
        quarter[next_quarter]+=1
        period_clock[next_quarter]=720
        team_fouls[next_quarter]=0;shot_clock[next_quarter]=24.;origin[next_quarter]=0
        next_period=quarter[next_quarter]
        side[next_quarter]=np.where((next_period==2)|(next_period==3),1-opening[next_quarter],opening[next_quarter])
        if possession_audit:
            pos_start[next_quarter]=elapsed[next_quarter];pos_origin[next_quarter]=7;pos_side[next_quarter]=side[next_quarter]
        tied=(clock<=0)&(team_points[:,0]==team_points[:,1])
        can_extend=tied & (overtime_count < (overtime.shape[2] if overtime is not None else 0))
        if can_extend.any():
            overtime_count[can_extend]+=1
            clock[can_extend]=300
            period_clock[can_extend]=300
            team_fouls[can_extend]=0;shot_clock[can_extend]=24.;origin[can_extend]=0
            side[can_extend]=rng.integers(0,2,int(can_extend.sum()))
            if possession_audit:
                pos_start[can_extend]=elapsed[can_extend];pos_origin[can_extend]=7;pos_side[can_extend]=side[can_extend]
    if not np.allclose(clock_ledger.sum(axis=1),elapsed,atol=1e-7):raise RuntimeError('Clock ledger does not reconcile')
    if not np.allclose(regulation_ledger.sum(axis=1),2880.,atol=1e-7):raise RuntimeError('Regulation clock ledger does not conserve 2880 seconds')
    fgm,threes,ftm,reb,ast,stl,blk,to=np.moveaxis(stats,2,0)
    scores=score_nba(platform,fgm=fgm,threes=threes,ftm=ftm,rebounds=reb,assists=ast,steals=stl,blocks=blk,turnovers=to)
    return {'scores':scores.astype(np.float32),'stats':stats,'team_points':team_points,
        'requires_overtime':team_points[:,0]==team_points[:,1], 'overtime_periods':overtime_count, 'elapsed_seconds':elapsed, 'counters':counters,
        'player_minutes':player_seconds/60,'personal_fouls':personal,'disqualified_at_seconds':dq_seconds,'attempts':attempts,'mechanics_counters':extra,
        'clock_audit':{'buckets':BUCKETS,'seconds':clock_ledger,'regulation_seconds':regulation_ledger,'actions':action_counts,'expirations':expiration_counts,'free_throw_administration_seconds':0.,'separate_transition_delay_seconds':0.},
        'possession_trace':{'enabled':possession_audit,'origins':possession_origins,'counts_by_team':pos_count,'completed_by_origin':pos_completed,'completed_seconds_by_origin':pos_seconds,'terminal_by_origin':pos_terminals,'terminal_seconds_by_origin':pos_terminal_seconds,'oreb_continuation_tails':oreb_tail_count,'oreb_continuation_tail_seconds':oreb_tail_seconds,'scenario_zero':sample_trace},
        'engine':'offline-integrated-basketball-v1','live_enabled':False}



