"""Experimental NBA orchestration boundary; Streamlit-free and not live-enabled."""
import numpy as np
from simmah_nba_candidates import build_candidates
from simmah_nba_field import build_field,sample_popularity_field
from simmah_nba_contest import evaluate_candidates,select_entries
from simmah_nba_rosters import export_entries,SLOT_COLUMNS


def run_pipeline(pool,outcome_factory,ownership,ownership_source,payouts,entry_fee,
                 portfolio_count,*,simulations=10000,candidate_target=5000,
                 field_support_target=10000,seed=83,diversity=50,salary_min=0,
                 max_ownership_error=5,progress=None,ownership_mode="projected"):

    """Generate three independent scenario sets and retain scored candidates.

    outcome_factory(count, seed) supplies shared slate outcomes aligned to pool.
    A validated pregame engine adapter must supply it; this orchestration does
    not invent projections, rotations, injuries or ownership data.
    """
    if ownership_mode not in {'projected','relative popularity'}:raise ValueError('Unknown ownership mode')
    if not isinstance(simulations,int) or simulations<1:raise ValueError('Positive simulation count required')
    if not np.isfinite(max_ownership_error) or max_ownership_error<0:raise ValueError('Valid ownership error tolerance required')
    def notify(message):
        if progress:progress(message)
    def draw(draw_seed):
        array=np.asarray(outcome_factory(simulations,draw_seed))
        if array.shape!=(simulations,len(pool)) or not np.isfinite(array).all():
            raise ValueError('Engine outcomes do not match simulation count and player order')
        return array.copy()
    notify('Simulating candidate scenarios')
    construction=draw(seed)
    candidates=build_candidates(pool,construction,target=candidate_target,seed=seed+1,salary_min=salary_min)
    if candidates['unique']<portfolio_count:raise ValueError('Insufficient unique NBA candidates for reserved entries')
    notify('Building independent opponent support')
    field_outcomes=draw(seed+1009)
    if np.array_equal(construction,field_outcomes):raise ValueError('Opponent scenarios repeat construction scenarios')
    support=build_candidates(pool,field_outcomes,target=field_support_target,seed=seed+1010)
    if ownership_mode=='projected':
        field=build_field(support['indices'],ownership,len(payouts)-1,seed+1011,ownership_source)
    else:
        field=sample_popularity_field(support['indices'],ownership,len(payouts)-1,seed+1011,ownership_source)
    if ownership_mode=='projected' and field['max_expected_error_pct']>max_ownership_error:
        raise ValueError(f"NBA field ownership mismatch {field['max_expected_error_pct']:.2f} percentage points exceeds tolerance")
    notify('Scoring independent evaluation scenarios')
    evaluation=draw(seed+2017)
    if np.array_equal(evaluation,construction) or np.array_equal(evaluation,field_outcomes):
        raise ValueError('Evaluation scenarios repeat construction or opponent scenarios')
    report=evaluate_candidates(evaluation,candidates['indices'],field['indices'],payouts,entry_fee,
        construction_seed=seed,evaluation_seed=seed+2017,field_copies=field['copies'])
    notify('Selecting portfolio')
    portfolio=select_entries(pool,candidates['indices'],report,portfolio_count,diversity=diversity)
    return {'candidates':candidates,'field':field,'report':report,'portfolio':portfolio,
            'simulation_seeds':{'construction':seed,'field':seed+1009,'evaluation':seed+2017},
            'simulations_per_set':simulations,'status':'experimental offline pipeline; marginal contest estimates'}


def export_portfolio(template,contest_id,pool,result):
    lineups=result['portfolio'][list(SLOT_COLUMNS)].astype(str).to_numpy().tolist()
    return export_entries(template,lineups,contest_id,pool,salary_cap=60000,max_from_team=4)
