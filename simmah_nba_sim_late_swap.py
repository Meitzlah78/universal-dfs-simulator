"""Conditional NBA late swap for unstarted games and verified final locked scores."""
import numpy as np
import pandas as pd
from simmah_nba_late_swap import entry_rows,locked_players,validate_swap
from simmah_nba_candidates import build_candidates
from simmah_nba_contest import evaluate_candidates
from simmah_nba_rules import rules_for


def final_scores(actuals,pool,required):
    """Missing actuals are errors, never assumed zeros or projected live scores."""
    if not required.any():return np.zeros(len(pool))
    if actuals is None or not {'Player ID','Actual Points','Status'}<=set(actuals):
        raise ValueError('Final locked-game scores require Player ID, Actual Points and Status columns')
    frame=actuals.copy();frame['Player ID']=frame['Player ID'].astype(str)
    if frame['Player ID'].duplicated().any():raise ValueError('Duplicate actual-score player IDs')
    frame=frame.set_index('Player ID').reindex(pool['Player ID'].astype(str))
    points=pd.to_numeric(frame['Actual Points'],errors='coerce').to_numpy(float)
    status=frame['Status'].astype(str).str.upper().eq('FINAL').to_numpy()
    if not (np.isfinite(points[required])&status[required]).all():
        raise ValueError('Every locked player used by entries or opponent field needs an explicit final site fantasy score. In-progress games are not supported.')
    return np.where(required,points,0.)


def simulate_swap_entries(template,contest_id,pool,outcome_factory,field,payouts,entry_fee,
                          actuals=None,*,now=None,salary_min=0,diversity=50,
                          simulations=10000,candidate_target=5000,seed=617,progress=None):
    """Use independent construction/evaluation draws; preserve exact locked slots.

    outcome_factory(count,seed,open_indices) simulates ONLY unstarted games and
    returns count x open_players. Field rosters/copies stay frozen from the build.
    This is marginal conditional contest evaluation, not live-game simulation.
    """
    pool=pool.reset_index(drop=True);rules=rules_for(pool);size=len(rules['slots'])
    entries=entry_rows(template,contest_id,pool);locked=locked_players(pool,now)
    lookup={str(pid):i for i,pid in enumerate(pool['Player ID'])}
    originals=np.array([[lookup[str(pid)] for pid in e[4:4+size]] for e in entries])
    field_ids=np.asarray(field['indices']);copies=np.asarray(field['copies'])
    if field_ids.ndim!=2 or field_ids.shape[1]!=size or field_ids.dtype.kind not in 'iu' or (field_ids<0).any() or (field_ids>=len(pool)).any():
        raise ValueError('Saved opponent field differs from this NBA slate')
    required=np.zeros(len(pool),bool);required[field_ids.ravel()]=True;required[originals.ravel()]=True;required &= locked
    actual=final_scores(actuals,pool,required);open_ids=np.flatnonzero(~locked)
    if not len(open_ids):raise ValueError('All games have started; no open slots to simulate')
    def draw(draw_seed):
        values=np.asarray(outcome_factory(simulations,draw_seed,open_ids))
        if values.shape!=(simulations,len(open_ids)) or not np.isfinite(values).all():raise ValueError('Remaining-game outcomes do not match open players')
        full=np.tile(actual,(simulations,1));full[:,open_ids]=values
        return full
    if progress:progress('Simulating unstarted games for replacement construction')
    construction=draw(seed)
    groups={}
    for entry_index,row in enumerate(originals):
        pattern=tuple((slot,int(index)) for slot,index in enumerate(row) if locked[index])
        groups.setdefault(pattern,[]).append(entry_index)
    candidates=[];by_pattern={};search=[]
    for group_number,(pattern,entry_indices) in enumerate(groups.items()):
        if len(pattern)==size:continue
        target=max(len(entry_indices),int(np.ceil(candidate_target/len(groups))))
        built=build_candidates(pool,construction,target=target,seed=seed+1+group_number,
            salary_min=salary_min,fixed_slots=dict(pattern),excluded_indices=np.flatnonzero(locked))
        rows=list(built['indices']);seen={tuple(sorted(row)) for row in rows}
        for entry_index in entry_indices:
            row=originals[entry_index]
            try:validate_swap(pool,row,row,locked,salary_min)
            except ValueError:continue
            if tuple(sorted(row)) not in seen:rows.append(row.copy());seen.add(tuple(sorted(row)))
        start=len(candidates);candidates.extend(rows);by_pattern[pattern]=np.arange(start,len(candidates))
        search.append({'locked_pattern':group_number,'requested':target,'unique':len(rows),'attempted':built['attempted']})
    if not candidates:raise ValueError('No legal replacement candidates found; original entries remain unchanged')
    candidates=np.asarray(candidates,dtype=int)
    if progress:progress('Evaluating replacements against frozen opponent field')
    evaluation=draw(seed+2017)
    if np.array_equal(construction[:,open_ids],evaluation[:,open_ids]):raise ValueError('Independent remaining-game evaluation outcomes required')
    report=evaluate_candidates(evaluation,candidates,field_ids,payouts,entry_fee,
        construction_seed=seed,evaluation_seed=seed+2017,field_copies=copies,score_ticks=rules['score_ticks'])
    used=np.zeros(len(pool));seen=set();output=[];diagnostics=[]
    metric=report['Top 1%'].to_numpy(float)
    for entry,row in zip(entries,originals):
        pattern=tuple((slot,int(index)) for slot,index in enumerate(row) if locked[index])
        eligible=by_pattern.get(pattern,np.array([],dtype=int));chosen=row;selected=None
        if len(eligible):
            utility=metric[eligible]-float(diversity)/100*used[candidates[eligible]].sum(axis=1)
            for candidate_index in eligible[np.argsort(-utility,kind='stable')]:
                candidate=candidates[candidate_index]
                if tuple(sorted(candidate)) in seen:continue
                validate_swap(pool,row,candidate,locked,salary_min)
                chosen=candidate;selected=int(candidate_index);break
        seen.add(tuple(sorted(chosen)));used[chosen]+=1
        output.append(pool.iloc[chosen]['Player ID'].astype(str).tolist())
        diagnostics.append({'Entry ID':entry[0],'Status':'Sim-selected' if selected is not None else 'Kept original',
            'Locked slots':len(pattern),'Changes':int((chosen!=row).sum()),
            'Salary':int(pool.iloc[chosen]['Salary'].sum()),
            'Conditional Top 1%':None if selected is None else float(metric[selected])})
    return {'lineups':output,'report':pd.DataFrame(diagnostics),'original_entries':entries,
            'candidate_report':report,'search':search,'simulations_per_set':simulations,
            'status':'Experimental conditional Top 1% selection against saved field; no in-progress game modeling'}
