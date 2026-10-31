"""Streaming contest evaluation with explicit sampled-field and tie accounting."""
import numpy as np
import pandas as pd


def lineup_indices(frame,slots,columns,multipliers=None):
    index={str(name):i for i,name in enumerate(columns)}
    try: picks=np.array([[index[str(name)] for name in row] for row in frame[slots].itertuples(index=False,name=None)],int)
    except KeyError as exc:raise ValueError('Lineup references a player missing from simulations: '+str(exc)) from exc
    mult=np.ones(len(slots)) if multipliers is None else np.asarray(multipliers,float)
    if np.all(mult==1):picks=np.sort(picks,axis=1)
    elif len(mult)>1 and np.all(mult[1:]==1):picks[:,1:]=np.sort(picks[:,1:],axis=1)
    return picks,mult


def score_batch(values,picks,multipliers):
    scores=np.zeros((len(values),len(picks)),np.float64)
    for slot,mult in enumerate(multipliers):scores+=values[:,picks[:,slot]]*mult
    return scores


def payout_vector(field_size,tiers):
    payouts=np.zeros(int(field_size),float);occupied=np.zeros(int(field_size),bool)
    for first,last,prize in tiers:
        first,last,prize=int(first),int(last),float(prize)
        if first<1 or last<first or prize<0 or not np.isfinite(prize):raise ValueError('Invalid payout tier')
        end=min(last,len(payouts))
        if first>len(payouts):continue
        if occupied[first-1:end].any():raise ValueError('Payout tiers overlap')
        occupied[first-1:end]=True;payouts[first-1:end]=prize
    return payouts


def evaluate_contest(outcomes,candidates,field,slots,field_size,tiers,entry_fee,
                     multipliers=None,joint=False,progress=None,batch_size=16):
    if candidates.empty or field.empty:raise ValueError('Candidates and opponent field must be nonempty')
    values=outcomes.to_numpy(np.float32)
    if not len(values) or not np.isfinite(values).all():raise ValueError('Invalid contest outcomes')
    field_size=int(field_size);own=len(candidates) if joint else 1
    if field_size<own:raise ValueError('More own entries than contest capacity')
    if not np.isfinite(entry_fee) or entry_fee<0:raise ValueError('Invalid entry fee')
    users,mult=lineup_indices(candidates,slots,outcomes.columns,multipliers)
    opponents,_=lineup_indices(field,slots,outcomes.columns,multipliers)
    from simmah_lineup_scores import LineupScorer
    from simmah_contest_scoring import score_insertion_bounds
    user_scorer = LineupScorer(users, mult, values.shape[1])
    field_scorer = LineupScorer(opponents, mult, values.shape[1])
    payouts=payout_vector(field_size,tiers);prefix=np.r_[0.,np.cumsum(payouts)]
    represented=max(0,field_size-own);scale=represented/len(field)
    n=len(candidates);prize_sum=np.zeros(n);rank_sum=np.zeros(n)
    hits={key:np.zeros(n) for key in ['WinRate','Top1','Top5','Top10','CashRate']}
    cuts={'WinRate':1,'Top1':max(1,int(np.ceil(.01*field_size))),
          'Top5':max(1,int(np.ceil(.05*field_size))),'Top10':max(1,int(np.ceil(.1*field_size)))}
    for start in range(0,len(values),batch_size):
        sample=values[start:start+batch_size]
        opponent_scores=np.sort(field_scorer(sample),axis=1)
        user_scores=user_scorer(sample)
        lower, upper = score_insertion_bounds(opponent_scores, user_scores)
        for scores,left,right in zip(user_scores,lower,upper):
            better=np.rint((len(field)-right)*scale).astype(int)
            equals=np.minimum(np.rint((right-left)*scale).astype(int),represented-better)
            if joint:
                sorted_own=np.sort(scores)
                own_left=np.searchsorted(sorted_own,scores,'left');own_right=np.searchsorted(sorted_own,scores,'right')
                better+=len(scores)-own_right
                equals+=own_right-own_left-1
            first=1+better;last=np.minimum(field_size,first+equals);ties=last-first+1
            prize=(prefix[last]-prefix[first-1])/ties
            prize_sum+=prize;rank_sum+=(first+last)/2
            for key,cut in cuts.items():hits[key]+=np.clip((cut-first+1)/ties,0,1)
            hits['CashRate']+=(prize>0)
        if progress:progress(min(1,(start+len(sample))/len(values)),f'Scoring contest: {min(start+len(sample),len(values)):,} / {len(values):,} outcomes')
    result=candidates.copy()
    for key,value in hits.items():result[key]=value/len(values)
    result['Estimated Full Field Rank']=rank_sum/len(values)
    result['FieldRank']=result['Estimated Full Field Rank']
    result['AvgPercentile']=1-(result['FieldRank']-1)/max(field_size-1,1)
    # Replace obsolete comparisons of lineup means with outcome-based ranks.
    result=result.drop(columns=['BeatsOpponents'],errors='ignore')
    result['FieldPercentile']=100*result['AvgPercentile']
    result['Expected Prize ($)']=prize_sum/len(values)
    result['Entry Fee ($)']=float(entry_fee)
    result['Expected Net ($)']=result['Expected Prize ($)']-float(entry_fee)
    result['Expected ROI (%)']=100*result['Expected Net ($)']/entry_fee if entry_fee else np.nan
    result['ContestScore']=result['Expected Net ($)']
    result.attrs.update(simulations=len(values),field_size=field_size,representative_opponents=len(field),
                        field_is_estimated=len(field)!=represented,joint=joint)
    return result
