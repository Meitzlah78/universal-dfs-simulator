"""Reconstructed offline regulation driver; never imported by production.

Not an exact recovery of the missing historical driver. Uses recovered training
clock distributions and frozen league play-call coefficients. Regulation only;
fixed own-25 kickoffs, approximate penalties/timeouts, no player projections.
"""
import numpy as np
from scipy.special import expit
from scipy.stats import norm, gamma

VERSION='nfl-clock-reconstruction-v1'


def transition(remaining,total,*,live=5.,stopped=False,warning_seen=False):
    """Sampled total already includes live time: never add live a second time.

    Warn only after a live play finishes; interrupt only runoff. Quarter runoff
    cannot cross the boundary. Plays begun before expiry still resolve outcomes.
    """
    r,t=np.broadcast_arrays(np.asarray(remaining,float),np.asarray(total,float))
    if not np.isfinite(r).all() or not np.isfinite(t).all() or (r<0).any() or (r>3600).any() or (t<0).any():
        raise ValueError('Invalid regulation clock input')
    if not np.isfinite(live) or live<0:raise ValueError('Invalid live duration')
    boundary=np.where(r%900==0,900,r%900)
    boundary=np.where(r==0,0,boundary)
    elapsed=np.minimum(t,boundary)
    threshold=np.where(r>1800,1920.,120.)
    crosses=(r>threshold)&(r-elapsed<=threshold)&~np.asarray(warning_seen)
    live_end=r-np.minimum(np.minimum(live,t),boundary)
    # A stopped-clock event has no outgoing runoff to interrupt.
    interrupt=crosses&(live_end>threshold)&~np.asarray(stopped)
    elapsed=np.where(interrupt,r-threshold,elapsed)
    return r-elapsed,elapsed,crosses


def state_pass_probability(model,remaining,down,togo,distance,margin,timeouts):
    m=margin/14;c=remaining/3600;d=np.log1p(togo)/4;f=distance/100
    rz=(f<=.2).astype(float);late=(c<1/12).astype(float)
    x=[m,c,d,f,rz,late,m*late,m*(1-c),m*m,d*d,f*f,np.full(len(c),.5),timeouts[:,0]/3,timeouts[:,1]/3]
    for v in (1,2,3,4):
        z=(down==v).astype(float);x.extend([z,z*d,z*f,z*rz])
    q=4-np.ceil(remaining/900).astype(int)+1
    x.extend([(q==v).astype(float) for v in (1,2,3,4)])
    return expit(np.column_stack(x)@np.asarray(model['decision']['coef'])[0]+model['decision']['intercept'][0])


def sample_clock(clock,kind,remaining,margin,u):
    late=((remaining<=120)|((remaining>1800)&(remaining<=1920)))
    script=np.where(late,np.where(margin<0,'late_trailing','late_other'),'ordinary')
    result=np.empty(len(remaining))
    for k in np.unique(kind):
        for s in np.unique(script[kind==k]):
            loc=(kind==k)&(script==s)
            groups=clock['classes'][str(k)]
            values=np.asarray(groups.get(str(s),groups.get('ordinary',[])),float)
            if not len(values) or (values<=0).any():raise ValueError('Unsupported clock profile')
            result[loc]=values[np.minimum((u[loc]*len(values)).astype(int),len(values)-1)]
    return result


def simulate(n,seed,clock,decision,parameters,*,fourth_policy=None,run_model=None):
    if n<1 or clock.get('train_years')!=[2022,2023]:raise ValueError('Training-only clock and positive draws required')
    rng=np.random.default_rng(seed);r=np.full(n,3600.);side=rng.integers(0,2,n);opening=side.copy()
    field=np.full(n,75.);down=np.ones(n,int);togo=np.full(n,10.);score=np.zeros((2,n));timeouts=np.full((2,n),3)
    env=np.clip(1+rng.normal(0,.1,n),.75,1.30);warning=np.zeros((2,n),bool);pending=np.ones(n,bool)
    counts={k:np.zeros(n) for k in ['snaps','drives','punts','non_redzone_tds','tds','fg_attempts','fg_made','turnovers','rush_attempts','rush_yards','rush20']}
    ledger={k:np.zeros(n) for k in ['running','incomplete','early_out_of_bounds','late_out_of_bounds','changed','kick','penalty','timeout']}
    for event in range(2500):
        if not (r>0).any():break
        # Fixed-width event streams keep arms paired without state-dependent RNG consumption.
        u=rng.random((n,14));i=np.flatnonzero(r>0);s=side[i].copy();margin=score[s,i]-score[1-s,i]
        q=4-np.ceil(r[i]/900).astype(int)+1
        isfourth=down[i]==4;go=(field[i]<5)|((r[i]<180)&(margin<0))
        if fourth_policy is not None and isfourth.any():
            import pandas as pd
            from simmah_nfl_event_levers_offline import predict_fourth
            j=i[isfourth]
            st=pd.DataFrame(dict(down=down[j],yardline_100=field[j],ydstogo=togo[j],game_seconds_remaining=r[j],score_differential=margin[isfourth],qtr=q[isfourth]))
            go[isfourth]=u[j,0]<predict_fourth(fourth_policy,st)
        kick=isfourth&~go
        penalty=(u[i,1]<parameters['penalty_rate'])&~kick
        normal=~kick&~penalty
        # New possession counts only when an offensive snap or kick actually occurs.
        begin=pending[i]&~penalty;counts['drives'][i[begin]]+=1;pending[i[begin]]=False
        gain=np.zeros(len(i));td=np.zeros(len(i),bool);turn=np.zeros(len(i),bool);safe=np.zeros(len(i),bool)
        kind=np.full(len(i),'running',dtype='U24');duration=np.zeros(len(i));changed=np.zeros(len(i),bool)
        kind[penalty]='penalty';duration[penalty]=5.
        counts['snaps'][i[normal]]+=1
        if normal.any():
            a=np.flatnonzero(normal);j=i[a]
            prob=state_pass_probability(decision,r[j],down[j],togo[j],field[j],margin[a],np.column_stack([timeouts[s[a],j],timeouts[1-s[a],j]]))
            passing=u[j,2]<prob;sack=passing&(u[j,3]<parameters['sack_rate'])
            intercept=passing&~sack&(u[j,4]<parameters['interception_rate'])
            caught=passing&~sack&~intercept&(u[j,5]<parameters['completion_rate'])
            running=~passing
            g=np.zeros(len(j));g[sack]=-np.clip(6+3*norm.ppf(u[j[sack],6]),1,15)
            g[caught]=np.clip(gamma.ppf(u[j[caught],6],a=1.5,scale=parameters['receiving_yards']/1.5)*env[j[caught]],0,85)
            if run_model is None:g[running]=np.clip((parameters['rushing_yards']+5.5*norm.ppf(u[j[running],6]))*np.sqrt(env[j[running]]),-5,65)
            else:
                from simmah_nfl_event_levers_offline import sample_gain
                g[running]=sample_gain(run_model,u[j[running],6],env[j[running]])
            g=np.clip(g,-(100-field[j]),field[j]);gain[a]=g
            fumble=(caught|running|sack)&~intercept&(u[j,7]<parameters['fumble_loss_rate'])
            turn[a]=intercept|fumble;td[a]=(g>=field[j])&~turn[a];safe[a]=(g<=-(100-field[j]))&~turn[a]
            counts['rush_attempts'][j[running]]+=1;counts['rush_yards'][j[running]]+=g[running];counts['rush20'][j[running&(g>=20)]]+=1
            incomplete=passing&~caught&~sack&~intercept
            oob=(caught|running)&(u[j,8]<parameters['oob_rate'])
            late=((q[a]==2)&(r[j]<=1920))|((q[a]==4)&(r[j]<=300))
            kind[a[incomplete]]='incomplete';kind[a[oob&~late]]='early_out_of_bounds';kind[a[oob&late]]='late_out_of_bounds'
            duration[a]=sample_clock(clock,kind[a],r[j],margin[a],u[j,9])
        if kick.any():
            a=np.flatnonzero(kick);j=i[a];fg=field[j]<=40;made=fg&(u[j,10]<np.clip(.97-.005*np.maximum(field[j]+17-30,0)-.009*np.maximum(field[j]+17-45,0),.35,.98))
            counts['punts'][j[~fg]]+=1;counts['fg_attempts'][j[fg]]+=1;counts['fg_made'][j[made]]+=1;score[s[a[made]],j[made]]+=3
            punt_new=np.clip(100-(100-field[j]+43+9*norm.ppf(u[j,11])),1,99);punt_new=np.where(punt_new<10,80,100-punt_new)
            # field is distance to opponent goal; touchback starts own 20.
            field[j]=np.where(fg,np.where(made,75,np.clip(100-field[j]-7,1,99)),punt_new)
            changed[a]=True;kind[a]='kick';duration[a]=7.
        if normal.any():
            a=np.flatnonzero(normal);j=i[a];old=field[j].copy();g=gain[a]
            counts['non_redzone_tds'][j[td[a]&(old>20)]]+=1;counts['tds'][j[td[a]]]+=1
            score[s[a[td[a]]],j[td[a]]]+=6+(u[j[td[a]],12]<parameters['extra_point_rate'])
            score[1-s[a[safe[a]]],j[safe[a]]]+=2
            counts['turnovers'][j[turn[a]]]+=1
            ordinary=~(td[a]|turn[a]|safe[a]);first=g>=togo[j]
            field[j[ordinary]]=old[ordinary]-g[ordinary]
            down[j[ordinary]]=np.where(first[ordinary],1,down[j[ordinary]]+1)
            togo[j[ordinary]]=np.where(first[ordinary],np.minimum(10,field[j[ordinary]]),togo[j[ordinary]]-g[ordinary])
            failed=ordinary&(down[j]>4)
            end=td[a]|turn[a]|safe[a]|failed;changed[a]=end
            field[j[turn[a]|failed]]=100-(old[turn[a]|failed]-g[turn[a]|failed])
            field[j[td[a]]]=75.;field[j[safe[a]]]=65.
            # Terminal plays consume live time only, not outgoing-drive runoff.
            kind[a[end]]='changed';duration[a[end]]=5.
        if changed.any():
            j=i[changed];side[j]=1-side[j];down[j]=1;togo[j]=np.minimum(10,field[j]);pending[j]=True
        # Approximate defensive timeout use, shared across all arms.
        timeout=(r[i]<=120)&(margin>0)&normal&~changed&(kind=='running')&(timeouts[1-s,i]>0)
        duration[timeout]=5.;kind[timeout]='timeout';timeouts[1-s[timeout],i[timeout]]-=1
        half=(r[i]>1800).astype(int);oldr=r[i].copy()
        after,elapsed,seen=transition(oldr,duration,stopped=np.isin(kind,['incomplete','late_out_of_bounds','changed','kick','penalty','timeout']),warning_seen=warning[half,i])
        warning[half,i]|=seen
        for k in ledger:ledger[k][i[kind==k]]+=elapsed[kind==k]
        r[i]=after
        halftime=(oldr>1800)&(after==1800)
        j=i[halftime]
        if len(j):side[j]=1-opening[j];field[j]=75;down[j]=1;togo[j]=10;pending[j]=True;timeouts[:,j]=3
    if (r>0).any():raise RuntimeError('Regulation failed to terminate')
    total=sum(ledger.values())
    if not np.allclose(total,3600,rtol=0,atol=1e-8):raise RuntimeError('Clock ledger not conserved')
    return {'version':VERSION,'means':{**{k:float(v.mean()) for k,v in counts.items()},'points':float(score.sum(axis=0).mean())},'clock_seconds':{k:float(v.mean()) for k,v in ledger.items()},'ledger_max_error':float(np.max(np.abs(total-3600))),'draws':n}
