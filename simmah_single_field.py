"""Batched FanDuel Single Game opponent proposals."""
import numpy as np
import pandas as pd


def build_fanduel_single_field(pool, mvp_weights, flex_weights, target, salary_range, rng=None, progress=None, max_proposals=None):
    rng = np.random.default_rng() if rng is None else rng
    target = int(target)
    slots = ['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5']
    low, high = float(salary_range[0]), min(float(salary_range[1]),60000)
    if target < 1 or len(pool) < 6 or not 0 <= low <= high:
        raise ValueError('Invalid Single Game field settings')
    names = pool.Name.astype(str).to_numpy()
    salary = pd.to_numeric(pool.Salary,errors='raise').to_numpy(float)
    points = pd.to_numeric(pool.Projection,errors='raise').to_numpy(float)
    teams = pool.Team.astype(str).to_numpy()
    if len(set(names)) != len(names) or not np.isfinite(salary).all() or (salary<=0).any() or not np.isfinite(points).all():
        raise ValueError('Invalid Single Game player pool')
    weights = [np.asarray(mvp_weights,float),np.asarray(flex_weights,float)]
    if any(w.shape != salary.shape or not np.isfinite(w).all() or (w<0).any() for w in weights):
        raise ValueError('Invalid Single Game ownership weights')
    weights[0] = np.maximum(weights[0],.01)
    limit = max(300000,target*15) if max_proposals is None else int(max_proposals)
    chunks=[]; accepted=attempted=0
    while accepted < target and attempted < limit:
        n=min(4096,limit-attempted);attempted+=n
        picks=np.full((n,6),-1,int);cost=np.zeros(n);alive=np.ones(n,bool)
        for slot in range(6):
            multiplier=1.5 if slot==0 else 1.
            valid=(cost[:,None]+salary[None,:]*multiplier<=high)
            if slot:
                valid &= ~(picks[:,:slot,None]==np.arange(len(pool))[None,None,:]).any(axis=1)
            mass=np.where(valid,weights[0 if slot==0 else 1],0)
            empty=mass.sum(axis=1)<=0
            # Match the old FLEX sampler's uniform fallback for zero weights.
            if slot:mass[empty]=valid[empty].astype(float)
            cumulative=np.cumsum(mass,axis=1);total=cumulative[:,-1]
            alive &= total>0
            index=(cumulative<=rng.random(n)[:,None]*total[:,None]).sum(axis=1).clip(max=len(pool)-1)
            picks[:,slot]=index;cost+=salary[index]*multiplier
        legal=alive&(cost>=low)&(cost<=high)
        legal &= (teams[picks]!=teams[picks[:,0,None]]).any(axis=1)
        chosen=picks[legal][:target-accepted];cost=cost[legal][:target-accepted]
        if len(chosen):
            data={slot:names[chosen[:,i]] for i,slot in enumerate(slots)}
            data.update(Salary=cost.astype(int),ProjectedPoints=np.round(points[chosen[:,0]]*1.5+points[chosen[:,1:]].sum(axis=1),2))
            chunks.append(pd.DataFrame(data));accepted+=len(chosen)
        if progress:progress(accepted/target,f'Building FanDuel Single Game opponents: {accepted:,} / {target:,}')
    if accepted < target:
        raise ValueError(f'Built {accepted:,} of {target:,} Single Game opponents; check salary range and available players')
    result=pd.concat(chunks,ignore_index=True)
    result.attrs.update(engine='batched-fd-single-field-v1',proposals=attempted)
    return result
