"""Batched NBA marginal contest scoring with exact integer field multiplicities."""
import numpy as np
import pandas as pd
from simmah_nba_arrays import score_batches
from simmah_nba_rosters import SLOT_COLUMNS
from simmah_portfolio_selection import select_portfolio


def evaluate_candidates(outcomes,candidates,field,payouts,entry_fee,*,construction_seed,
                        evaluation_seed,field_copies=None,batch_size=128):
    """Score one candidate inserted into the supplied opponent field.

    Payouts are per finishing position, including zero-paid positions. Duplicate
    opponent lineups may be compressed with positive integer multiplicities.
    Other selected user entries are not inserted here: this is marginal lineup
    evaluation, not a joint portfolio payout simulation. Seeds must represent
    independently generated construction and evaluation outcomes.
    """
    if construction_seed==evaluation_seed:raise ValueError('Independent evaluation seed required')
    c=np.asarray(candidates);f=np.asarray(field);prize=np.asarray(payouts,float)
    if c.ndim!=2 or f.ndim!=2 or c.shape[1]!=9 or f.shape[1]!=9 or not len(c) or not len(f):
        raise ValueError('Nonempty nine-player candidate and field arrays required')
    for ids in (c,f):
        if ids.dtype.kind not in 'iu' or (np.diff(np.sort(ids,axis=1),axis=1)==0).any():
            raise ValueError('Nine distinct integer player indices required per lineup')
    copies=np.ones(len(f),dtype=np.int64) if field_copies is None else np.asarray(field_copies)
    if copies.shape!=(len(f),) or copies.dtype.kind not in 'iu' or (copies<=0).any():
        raise ValueError('Positive integer opponent multiplicities required')
    count=int(copies.sum())+1
    if prize.shape!=(count,) or not np.isfinite(prize).all() or (prize<0).any() or (np.diff(prize)>0).any():
        raise ValueError('Exact nonincreasing payout vector must cover the whole contest')
    if not np.isfinite(entry_fee) or entry_fee<=0:raise ValueError('Positive entry fee required')
    prefix=np.r_[0.,np.cumsum(prize)]
    totals=np.zeros((len(c),5));simulations=0
    cb=score_batches(outcomes,c,batch_size);fb=score_batches(outcomes,f,batch_size)
    for (start,cs),(other,fs) in zip(cb,fb):
        # FanDuel basketball scores have 0.1-point precision. Integer ticks
        # prevent float summation order from breaking exact ties.
        cs=np.rint(cs.T*10).astype(np.int64);fs=np.rint(fs.T*10).astype(np.int64)
        for j in range(len(cs)):
            order=np.argsort(fs[j],kind='stable');scores=fs[j,order]
            cumulative=np.r_[0,np.cumsum(copies[order])]
            left=np.searchsorted(scores,cs[j],side='left');right=np.searchsorted(scores,cs[j],side='right')
            above=count-1-cumulative[right];ties=cumulative[right]-cumulative[left]+1
            winnings=(prefix[above+ties]-prefix[above])/ties
            def top(k):return np.clip(k-above,0,ties)/ties
            totals[:,0]+=winnings;totals[:,1]+=top(1)
            totals[:,2]+=top(max(1,int(np.ceil(count*.01))))
            totals[:,3]+=top(int((prize>0).sum()));totals[:,4]+=cs[j]/10
        simulations+=len(cs)
    if not simulations:raise ValueError('Nonempty evaluation simulations required')
    totals/=simulations
    report=pd.DataFrame({'Expected Prize ($)':totals[:,0],'Win %':100*totals[:,1],
                         'Top 1%':100*totals[:,2],'Cash %':100*totals[:,3],
                         'Evaluation Mean Points':totals[:,4]})
    report['Entry Fee ($)']=entry_fee
    report['Expected Net ($)']=report['Expected Prize ($)']-entry_fee
    report['Expected ROI (%)']=100*report['Expected Net ($)']/entry_fee
    report.attrs.update({'contest_entries':count,'simulations':simulations,
                         'evaluation':'marginal lineup, exact supplied opponent multiplicities'})
    return report


def select_entries(pool,candidates,report,count,diversity=50,controls=None,metric='Top 1%'):
    """Reselect saved scored candidates; no simulation or field rebuilding."""
    indices=np.asarray(candidates)
    if len(indices)!=len(report):raise ValueError('Candidate report alignment mismatch')
    rows=report.reset_index(drop=True).copy()
    for slot,column in enumerate(SLOT_COLUMNS):
        rows[column]=pool.iloc[indices[:,slot]]['Player ID'].astype(str).to_numpy()
    return select_portfolio(rows,list(SLOT_COLUMNS),count,metric,
                            controls=controls,diversity=diversity)
