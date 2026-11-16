"""Cap-constrained quality optimum followed by budgeted concentration.

Optional exact pregame bounds tighten the NBA FanDuel concentration solve.
No caps are relaxed and the quality budget is unchanged.
"""
import math
from time import perf_counter
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import milp,Bounds,LinearConstraint
from simmah_exposure_limits import validate_exposure_limits

VERSION='portfolio-quality-budget-v1'
QUALITY_LOSS=.05


class CapConflict(ValueError):pass
class QualityNotCertified(RuntimeError):pass


def select_quality_budget(candidates,slots,count,*,controls=None,automatic_max=80.,
                          quality_metric='Top1',quality_loss=QUALITY_LOSS,time_limit=15.,diversify=True,tighten=False):
    started=perf_counter()
    controls=controls or {};count=int(count)
    if count<1 or not 0<=quality_loss<1 or not 0<=automatic_max<=100 or time_limit<=0:
        raise ValueError('Invalid budget, cap, count, or solver limit')
    if not slots or quality_metric not in candidates or not set(slots)<=set(candidates):
        raise ValueError('Missing roster or quality columns')
    q=pd.to_numeric(candidates[quality_metric],errors='coerce')
    if not np.isfinite(q).all() or (q<0).any():raise ValueError('Finite nonnegative pregame quality required')
    if q.max()<=0:raise ValueError('No positive measured pregame quality')
    special=next((s for s in slots if s in ('Captain','MVP')),None)
    if special and slots[0]!=special:raise ValueError('Special role must be first')
    def key(r):return ((str(r[special]),) if special else ())+tuple(sorted(str(r[s]) for s in slots if s!=special))
    c=candidates.assign(_q=q).sort_values('_q',ascending=False,kind='stable').copy()
    c=c.loc[~c.apply(key,axis=1).duplicated()].reset_index(drop=True)
    if c[slots].isna().any().any() or any(len(set(r))!=len(slots) for r in c[slots].to_numpy()):
        raise ValueError('Missing or repeated roster player')
    if len(c)<count:raise CapConflict(f'Only {len(c)} unique candidates for {count} entries; no limits relaxed')
    quality=c._q.to_numpy(float);scaled=quality/quality.max();m=len(c)
    names=sorted(set(c[slots].values.ravel())|set(controls));index={n:i for i,n in enumerate(names)};p=len(names)
    picks=np.array([[index[n] for n in row] for row in c[slots].to_numpy()])
    overall=sparse.csr_matrix((np.ones(m*len(slots)),(picks.ravel(),np.repeat(np.arange(m),len(slots)))),shape=(p,m))
    rows=[sparse.csr_matrix(np.ones((1,m)))];lower=[count];upper=[count];labels=['portfolio count']
    def pct(cfg,key,default):
        v=float(cfg.get(key,default))
        if not np.isfinite(v) or not 0<=v<=100:raise ValueError('Invalid exposure percent: '+key)
        return v
    def add_constraints(matrix,role):
        rows.append(matrix)
        for name in names:
            cfg=controls.get(name,{})
            if role=='Overall':
                lo=100. if cfg.get('Lock',False) else pct(cfg,'Min Exposure %',0.)
                hi=min(pct(cfg,'Max Exposure %',100.),automatic_max)
                if cfg.get('Fade',False):hi=0.
            else:
                lo=pct(cfg,role+' Min %',0.);hi=pct(cfg,role+' Max %',100.)
            l=math.ceil(count*lo/100-1e-9);u=math.floor(count*hi/100+1e-9)
            if l>u:raise CapConflict(f'{name}: {role} minimum {l} exceeds capped maximum {u}; no limits relaxed')
            lower.append(l);upper.append(u);labels.append(name+' '+role)
    add_constraints(overall,'Overall')
    if special:
        role=sparse.csr_matrix((np.ones(m),(picks[:,0],np.arange(m))),shape=(p,m))
        add_constraints(role,'Captain' if special=='Captain' else 'MVP')
        add_constraints(overall-role,'Flex')
    a=sparse.vstack(rows,format='csc');lo=np.asarray(lower,float);hi=np.asarray(upper,float)
    limits=LinearConstraint(a,lo,hi);opts={'time_limit':float(time_limit),'mip_rel_gap':0.}
    first_started=perf_counter()
    first=milp(-scaled,integrality=np.ones(m),bounds=Bounds(np.zeros(m),np.ones(m)),constraints=limits,options=opts)
    first_seconds=perf_counter()-first_started
    if first.status==2:raise CapConflict('No full portfolio satisfies the manual and automatic caps in this candidate pool; no limits relaxed')
    if first.status!=0 or first.x is None:
        raise QualityNotCertified('Highest-quality feasible portfolio was not certified before solver termination; no caps relaxed')
    chosen=np.flatnonzero(first.x>.5)
    def check(ids):
        x=np.zeros(m);x[ids]=1;actual=a@x
        if len(ids)!=count or (actual<lo-1e-7).any() or (actual>hi+1e-7).any():
            raise RuntimeError('Solver incumbent failed independent count/exposure validation')
    check(chosen)
    optimum=float(quality[chosen].sum());scaled_opt=float(scaled[chosen].sum());floor=(1-quality_loss)*scaled_opt
    original=chosen.copy();best_concentration=float(np.square(np.asarray(overall[:,original].sum(axis=1)).ravel()).sum())
    second_seconds=0.;second=None;retained=m;original_m=m
    def finish(chosen,status,optimal):
        actual_quality=float(quality[chosen].sum())
        if actual_quality<optimum*(1-quality_loss)-1e-9:raise RuntimeError('Quality-loss budget exceeded')
        result=c.iloc[chosen].drop(columns='_q').copy().reset_index(drop=True)
        validate_exposure_limits(result,slots,controls)
        exposure=np.asarray(overall[:,chosen].sum(axis=1)).ravel()
        result.attrs.update(version=VERSION,quality_optimum=optimum,
            selected_quality=actual_quality,quality_loss_budget=quality_loss,
            actual_quality_loss=(optimum-actual_quality)/optimum,automatic_cap_pct=automatic_max,
            effective_automatic_cap_pct=automatic_max,max_exposure_pct=float(exposure.max()*100/count),
            concentration_before=best_concentration,concentration_after=float(np.square(exposure).sum()),
            quality_optimality='certified by MILP',diversity_status=status,
            diversity_optimal=optimal,diversity_requested=bool(diversify),unique_candidates=original_m,
            formulation='tightened exact epigraph' if tighten else 'original epigraph',
            quality_solve_seconds=first_seconds,concentration_solve_seconds=second_seconds,
            total_seconds=perf_counter()-started,retained_candidates=retained,
            quality_mip_gap=getattr(first,'mip_gap',None),
            concentration_mip_gap=getattr(second,'mip_gap',None),
            concentration_dual_bound=getattr(second,'mip_dual_bound',None),
            concentration_status_code=getattr(second,'status',None))
        return result
    if not diversify:return finish(chosen,'diversity disabled; retained certified quality optimum',True)
    # For integer exposure k, max_j[(2j+1)k-j(j+1)] = k^2.
    # This epigraph gives an exact squared-concentration objective without
    # enumerating portfolio pairs or changing the primary quality budget.
    # A candidate cannot be in a budget-feasible portfolio if even the
    # globally strongest other count-1 candidates cannot raise it to the floor.
    # This is a pregame upper-bound proof, not a heuristic top-N truncation.
    keep=np.ones(m,dtype=bool)
    if tighten:
        keep[count:]=scaled[count:]+scaled[:count-1].sum()>=floor-1e-9
    kept=np.flatnonzero(keep);retained=len(kept)
    work_overall=overall[:,kept];work_a=a[:,kept];work_scaled=scaled[kept]
    min_counts=np.zeros(p,dtype=int);max_counts=np.full(p,count,dtype=int)
    if tighten:
        # For each exposure count k, ignore all other caps and bound the best
        # attainable quality by taking the top k containing and count-k other
        # candidates. Excluding k below the floor preserves every feasible roster.
        for player in range(p):
            has=np.asarray(work_overall.getrow(player).toarray()).ravel()>0
            yes=np.r_[0.,np.cumsum(work_scaled[has])]
            no=np.r_[0.,np.cumsum(work_scaled[~has])]
            feasible=[k for k in range(count+1) if k<len(yes) and count-k<len(no)
                      and yes[k]+no[count-k]>=floor-1e-9
                      and lo[1+player]<=k<=hi[1+player]]
            if not feasible:raise RuntimeError('Quality/exposure bound excluded certified optimum')
            min_counts[player]=min(feasible);max_counts[player]=max(feasible)
    tangents=[];tl=[]
    if not tighten:
        # Preserve the live formulation's block ordering for a fair benchmark.
        for k in range(count):
            tangents.append(sparse.hstack([-(2*k+1)*work_overall,sparse.eye(p)],format='csc'))
            tl.extend([-k*(k+1)]*p)
    else:
        for player in range(p):
            for k in range(min_counts[player],max_counts[player]):
                unit=sparse.csr_matrix(([1.],([0],[player])),shape=(1,p))
                tangents.append(sparse.hstack([-(2*k+1)*work_overall.getrow(player),unit],format='csc'))
                tl.append(-k*(k+1))
    base=[sparse.hstack([work_a,sparse.csr_matrix((a.shape[0],p))]),
          sparse.csr_matrix(np.r_[work_scaled,np.zeros(p)][None,:])]
    l2=list(lo)+[floor];u2=list(hi)+[np.inf]
    if tighten:
        base.append(sparse.hstack([work_overall,sparse.csr_matrix((p,p))]))
        l2.extend(min_counts);u2.extend(max_counts)
        # Certified quality optimum is a known feasible concentration incumbent.
        base.append(sparse.csr_matrix(np.r_[-1e-6*work_scaled,np.ones(p)][None,:]))
        l2.append(-np.inf);u2.append(best_concentration-1e-6*scaled_opt+1e-8)
    a2=sparse.vstack([*base,*tangents],format='csc')
    l2=np.r_[l2,tl];u2=np.r_[u2,np.full(len(tl),np.inf)]
    objective=np.r_[-1e-6*work_scaled,np.ones(p)]
    second_started=perf_counter()
    second=milp(objective,integrality=np.r_[np.ones(retained),np.zeros(p)],
        bounds=Bounds(np.r_[np.zeros(retained),min_counts**2],
                      np.r_[np.ones(retained),max_counts**2]),
        constraints=LinearConstraint(a2,l2,u2),options=opts)
    second_seconds=perf_counter()-second_started
    second_status='optimal concentration' if second.status==0 else 'time-limited feasible concentration'
    if second.x is not None:
        trial=kept[np.flatnonzero(second.x[:retained]>.5)];check(trial)
        if float(scaled[trial].sum())<floor-1e-7:raise RuntimeError('Solver violated frozen quality-loss budget')
        concentration=float(np.square(np.asarray(overall[:,trial].sum(axis=1)).ravel()).sum())
        if concentration<=best_concentration:chosen=trial
    else:second_status='diversity search unfinished; retained certified quality optimum'
    return finish(chosen,second_status,bool(second.status==0))
