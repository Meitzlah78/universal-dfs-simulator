"""Batched NBA marginal contest scoring with exact integer field multiplicities."""
import numpy as np
import pandas as pd
from simmah_nba_arrays import score_batches
from simmah_nba_rules import rules_for
from simmah_selector_budget import select_quality_budget,VERSION


def evaluate_candidates(outcomes,candidates,field,payouts,entry_fee,*,construction_seed,
                        evaluation_seed,field_copies=None,batch_size=128,score_ticks=10):
    """Score one candidate inserted into the supplied opponent field.

    Payouts are per finishing position, including zero-paid positions. Duplicate
    opponent lineups may be compressed with positive integer multiplicities.
    Other selected user entries are not inserted here: this is marginal lineup
    evaluation, not a joint portfolio payout simulation. Seeds must represent
    independently generated construction and evaluation outcomes.
    """
    if construction_seed==evaluation_seed:raise ValueError('Independent evaluation seed required')
    c=np.asarray(candidates);f=np.asarray(field);prize=np.asarray(payouts,float)
    if c.ndim!=2 or f.ndim!=2 or c.shape[1] not in {8,9} or f.shape[1]!=c.shape[1] or not len(c) or not len(f):
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
    cash_places=int(np.count_nonzero(prize>0))
    totals=np.zeros((len(c),5));simulations=0
    cb=score_batches(outcomes,c,batch_size);fb=score_batches(outcomes,f,batch_size)
    for (start,cs),(other,fs) in zip(cb,fb):
        # FanDuel basketball scores have 0.1-point precision. Integer ticks
        # prevent float summation order from breaking exact ties.
        cs=np.rint(cs.T*score_ticks).astype(np.int64);fs=np.rint(fs.T*score_ticks).astype(np.int64)
        for j in range(len(cs)):
            low=int(fs[j].min());high=int(fs[j].max());span=high-low+1
            # Integer score ticks permit exact weighted rank lookup without
            # sorting every opponent roster in every simulated contest.
            # Bound memory for unusual user-supplied score ranges; retain the
            # original sort path when a histogram would be wasteful.
            if span<=65536 and count<=2**53:
                histogram=np.bincount(fs[j]-low,weights=copies,minlength=span).astype(np.int64)
                cumulative=np.r_[0,np.cumsum(histogram)]
                left=np.clip(cs[j]-low,0,span)
                right=np.clip(cs[j]-low+1,0,span)
            else:
                order=np.argsort(fs[j],kind='stable');scores=fs[j,order]
                cumulative=np.r_[0,np.cumsum(copies[order])]
                left=np.searchsorted(scores,cs[j],side='left');right=np.searchsorted(scores,cs[j],side='right')
            above=count-1-cumulative[right];ties=cumulative[right]-cumulative[left]+1
            winnings=(prefix[above+ties]-prefix[above])/ties
            def top(k):return np.clip(k-above,0,ties)/ties
            totals[:,0]+=winnings;totals[:,1]+=top(1)
            totals[:,2]+=top(max(1,int(np.ceil(count*.01))))
            totals[:,3]+=top(cash_places);totals[:,4]+=cs[j]/score_ticks
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
    if metric not in report:raise ValueError('Requested ranking metric is unavailable')
    indices=np.asarray(candidates)
    if len(indices)!=len(report):raise ValueError('Candidate report alignment mismatch')
    rows=report.reset_index(drop=True).copy()
    for slot,column in enumerate(rules_for(pool)['slots']):
        rows[column]=pool.iloc[indices[:,slot]]['Player ID'].astype(str).to_numpy()
    from simmah_nba_portfolio_limits import portfolio_limits, validate_portfolio_limits
    limits=portfolio_limits(pool,controls,count=int(count))
    quality_metric=metric
    if metric=='Expected ROI (%)':
        # Same ranking/optimum for a common entry fee; a percentage budget on
        # negative ROI has no useful meaning. Budget expected payout instead.
        quality_metric='Expected Prize ($)'
        if quality_metric not in rows:
            if 'Entry Fee ($)' not in rows:raise ValueError('ROI selection requires expected prize or entry fee')
            fee=pd.to_numeric(rows['Entry Fee ($)'],errors='coerce')
            if not np.isfinite(fee).all() or (fee<=0).any() or fee.nunique()!=1:raise ValueError('One positive common entry fee required')
            rows[quality_metric]=fee*(1+pd.to_numeric(rows[metric],errors='coerce')/100)
    budget=.05 if diversity is None or float(diversity)>0 else 0.
    selected=select_quality_budget(rows,list(rules_for(pool)['slots']),count,
        controls=limits,automatic_max=100.,quality_metric=quality_metric,quality_loss=budget,diversify=budget>0)
    selected.attrs.update(portfolio_selection='nba-'+VERSION,ranking_metric=metric,
        budget_metric=quality_metric,selection_method='certified quality then budgeted concentration' if budget>0 else 'certified maximum quality; diversity disabled')
    validate_portfolio_limits(selected,rules_for(pool)['slots'],limits)
    selected.attrs['nba_hard_exposure_limits']=limits
    if not selected.attrs.get('diversity_optimal',True):
        import logging
        logging.getLogger(__name__).warning('NBA selector: %s',selected.attrs['diversity_status'])
    return selected




def selection_key(pool,candidates,report,count,diversity,metric):
    """Identity for reselecting immutable saved candidates without rerunning MILP."""
    import hashlib,json
    from simmah_nba_portfolio_limits import portfolio_limits
    cols=list(dict.fromkeys(c for c in [metric,'Expected Prize ($)','Entry Fee ($)'] if c in report))
    digest=hashlib.sha256(np.asarray(candidates).tobytes()+pd.util.hash_pandas_object(report[cols],index=True).values.tobytes())
    digest.update(json.dumps({'version':VERSION,'ids':pool['Player ID'].astype(str).tolist(),
        'limits':portfolio_limits(pool,count=int(count)),'count':int(count),'metric':metric,
        'budget':.05 if diversity is None or float(diversity)>0 else 0.,
        'diversify':diversity is None or float(diversity)>0},sort_keys=True,default=str).encode())
    return digest.hexdigest()


def reselect_saved_entries(pool,built,diversity,metric):
    count=len(built['portfolio']);key=selection_key(pool,built['candidates']['indices'],built['report'],count,diversity,metric)
    if built.get('selection_key')==key:return built['portfolio']
    # Commit only after selection + cap validation succeeds. Failure leaves both
    # the saved portfolio and its successful request key untouched.
    try:selected=select_entries(pool,built['candidates']['indices'],built['report'],count,diversity=diversity,metric=metric)
    except (ValueError,RuntimeError):
        import logging
        logging.getLogger(__name__).warning('NBA reselection failed; previous saved portfolio retained',exc_info=True)
        raise
    built['portfolio']=selected;built['selection_key']=key
    return selected
