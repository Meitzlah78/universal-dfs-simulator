"""Offline dependence-only ablation; no game-state or causal blowout model."""
import numpy as np
from simmah_nba_minutes import draw_regulation_minutes

VERSION='shared-bench-dependence-v1-offline'


def draw_bench_minutes(means,trials,seed,*,shared=True):
    """Preserve production's 20% +swing / 80% -swing/4 marginal law.

    The only treatment is one common sign across disjoint reserve/donor pairs.
    All pairs use baseline minutes and distinct players, so shared signs cannot
    change another pair's feasible transfer amplitude. Each player's conditional
    expected transfer remains zero. This is a latent regime hypothesis only.
    """
    means=np.asarray(means,float)
    seq=seed if isinstance(seed,np.random.SeedSequence) else np.random.SeedSequence(seed)
    v=draw_regulation_minutes(means,trials,seq)
    rng=np.random.default_rng(np.random.SeedSequence(seq.entropy,
        spawn_key=(*seq.spawn_key,0),pool_size=seq.pool_size))
    reserve=np.flatnonzero((means>0)&(means<18));donor=np.flatnonzero((means>=18)&(means<48))
    ranks=min(len(reserve),len(donor))
    if not ranks:return v
    rows=np.arange(trials)
    r=reserve[np.argsort(rng.random((trials,len(reserve))),axis=1)]
    d=donor[np.argsort(rng.random((trials,len(donor))),axis=1)]
    regime=None
    for k in range(ranks):
        i,j=r[:,k],d[:,k]
        swing=np.minimum.reduce([np.full(trials,12.),48-v[rows,i],v[rows,j],4*v[rows,i],4*(48-v[rows,j])])
        if not shared or regime is None:regime=rng.random(trials)<.2
        transfer=swing*np.where(regime,1.,-.25)
        v[rows,i]+=transfer;v[rows,j]-=transfer
    return v
