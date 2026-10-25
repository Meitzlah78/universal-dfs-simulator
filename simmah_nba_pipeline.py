"""Experimental NBA orchestration boundary; Streamlit-free and not live-enabled."""
import numpy as np
from copy import deepcopy
from time import perf_counter
from simmah_nba_candidates import build_candidates,build_opponent_support
from simmah_nba_field import build_field,sample_popularity_field,ownership_support_diagnostic
from simmah_nba_contest import evaluate_candidates,select_entries
from simmah_nba_rosters import export_entries,SLOT_COLUMNS
from simmah_nba_rules import rules_for
from simmah_nba_pregame import validate_game_reports


def run_pipeline(pool,outcome_factory,ownership,ownership_source,payouts,entry_fee,
                 portfolio_count,*,simulations=10000,candidate_target=5000,
                 field_support_target=10000,seed=83,diversity=50,salary_min=0,
                 max_ownership_error=5,progress=None,ownership_mode="projected",correlation=0,
                 excluded_indices=None,capture_diagnostics=False):

    """Generate three independent scenario sets and retain scored candidates.

    outcome_factory(count, seed) supplies shared slate outcomes aligned to pool.
    A validated pregame engine adapter must supply it; this orchestration does
    not invent projections, rotations, injuries or ownership data.
    """
    if ownership_mode not in {'projected','relative popularity'}:raise ValueError('Unknown ownership mode')
    if not isinstance(simulations,int) or simulations<1:raise ValueError('Positive simulation count required')
    if not np.isfinite(max_ownership_error) or max_ownership_error<0:raise ValueError('Valid ownership error tolerance required')
    if hasattr(outcome_factory,'set_progress'):outcome_factory.set_progress(progress)
    excluded=np.asarray([] if excluded_indices is None else excluded_indices)
    if excluded.ndim!=1 or (excluded.size and (excluded.dtype.kind not in 'iu' or (excluded<0).any() or (excluded>=len(pool)).any())):
        raise ValueError('Valid original-pool player indices required for exclusions')
    excluded=excluded.astype(int)
    timings={'game_scenarios':0.};cache_hits=0
    captured_draws={};captured_reports={}
    def notify(message):
        if progress:progress(message)
    def draw(draw_seed):
        nonlocal cache_hits
        started=perf_counter()
        array=np.asarray(outcome_factory(simulations,draw_seed))
        timings['game_scenarios']+=perf_counter()-started
        cache_hits+=int(bool(getattr(outcome_factory,'last_cache_hit',False)))
        if array.shape!=(simulations,len(pool)) or not np.isfinite(array).all():
            raise ValueError('Engine outcomes do not match simulation count and player order')
        validate_game_reports(getattr(outcome_factory,'last_report',[]))
        if capture_diagnostics:
            captured_draws[str(draw_seed)]=array.copy()
            captured_reports[str(draw_seed)]=deepcopy(getattr(outcome_factory,'last_report',[]))
        return array.copy()
    notify('Simulating candidate scenarios')
    construction=draw(seed)
    started=perf_counter()
    candidates=build_candidates(pool,construction,target=candidate_target,seed=seed+1,salary_min=salary_min,correlation=correlation,
                                excluded_indices=excluded)
    timings['candidates']=perf_counter()-started
    if candidates['unique']<portfolio_count:raise ValueError('Insufficient unique NBA candidates for reserved entries')
    notify('Building independent opponent support')
    field_outcomes=draw(seed+1009)
    started=perf_counter()
    if np.array_equal(construction,field_outcomes):raise ValueError('Opponent scenarios repeat construction scenarios')
    if ownership_mode=='projected':
        support=build_opponent_support(pool,field_outcomes,ownership,target=field_support_target,seed=seed+1010)
    else:
        support=build_candidates(pool,field_outcomes,target=field_support_target,seed=seed+1010)
    fallback_reason=None
    if ownership_mode=='projected':
        try:
            field=build_field(support['indices'],ownership,len(payouts)-1,seed+1011,ownership_source)
            residual=field['max_expected_error_pct']
            if residual>max_ownership_error:
                fallback_reason=f"Projected ownership fit missed by {residual:.2f} percentage points (limit {max_ownership_error:g})."
        except ValueError as exc:
            if str(exc)!='Ownership targets include players absent from legal field support':raise
            fallback_reason=str(exc)
        if fallback_reason:
            diagnostic=ownership_support_diagnostic(support['indices'],ownership,max_ownership_error)
            if diagnostic['status']=='support-limited':
                fallback_reason+=f" Generated legal roster support cannot meet tolerance; best possible maximum error is {diagnostic['minimum_max_error_pct']:.2f} points."
            elif diagnostic['status']=='feasible':
                fallback_reason+=" Generated roster support can meet tolerance; ownership optimizer did not reach an acceptable fit."
            else:
                fallback_reason+=" Support feasibility check was inconclusive."
            # A failed marginal fit does not invalidate already-validated source
            # inputs. Preserve their relative popularity instead of flattening
            # every legal roster to equal probability. This is NOT a fitted field.
            field=sample_popularity_field(support['indices'],ownership,len(payouts)-1,
                seed+1011,'Validated ownership used only as relative popularity: '+ownership_source)
            field['fallback_mode']='relative popularity from validated ownership'
            field['max_expected_error_pct']=float(abs(field['ownership_expected']-np.asarray(ownership,float)).max())
            field['ownership_fit_diagnostic']=diagnostic
            field['ownership_fit_warning']=fallback_reason
            field['ownership_target']=np.asarray(ownership,float).copy()
    else:
        field=sample_popularity_field(support['indices'],ownership,len(payouts)-1,seed+1011,ownership_source)
    timings['opponent_field']=perf_counter()-started
    notify('Scoring independent evaluation scenarios')
    evaluation=draw(seed+2017)
    if np.array_equal(evaluation,construction) or np.array_equal(evaluation,field_outcomes):
        raise ValueError('Evaluation scenarios repeat construction or opponent scenarios')
    started=perf_counter()
    report=evaluate_candidates(evaluation,candidates['indices'],field['indices'],payouts,entry_fee,
        construction_seed=seed,evaluation_seed=seed+2017,field_copies=field['copies'],score_ticks=rules_for(pool)['score_ticks'])
    timings['contest_scoring']=perf_counter()-started
    notify('Selecting portfolio')
    portfolio=select_entries(pool,candidates['indices'],report,portfolio_count,diversity=diversity)
    result={'candidates':candidates,'field':field,'report':report,'portfolio':portfolio,
            'timings_seconds':timings,'scenario_cache_hits':cache_hits,
            'excluded_player_ids':pool.iloc[excluded]['Player ID'].astype(str).tolist(),
            'simulation_seeds':{'construction':seed,'field':seed+1009,'evaluation':seed+2017},
            'simulations_per_set':simulations,'status':'experimental offline pipeline; marginal contest estimates'}
    if capture_diagnostics:
        result['diagnostics']={'outcomes':captured_draws,'engine_reports':captured_reports,
            'support':support,'ownership_input':np.asarray(ownership).copy(),
            'payouts':np.asarray(payouts).copy(),
            'settings':{'simulations':simulations,'candidate_target':candidate_target,
                'field_support_target':field_support_target,'seed':seed,'diversity':diversity,
                'salary_min':salary_min,'max_ownership_error':max_ownership_error,
                'ownership_mode':ownership_mode,'ownership_source':ownership_source,
                'correlation':correlation,'entry_fee':entry_fee,'portfolio_count':portfolio_count},
            'seeds':{'candidate_search':seed+1,'support_search':seed+1010,'field_copies':seed+1011}}
    return result


def export_portfolio(template,contest_id,pool,result):
    lineups=result['portfolio'][list(rules_for(pool)['slots'])].astype(str).to_numpy().tolist()
    return export_entries(template,lineups,contest_id,pool,salary_cap=rules_for(pool)['salary_cap'],max_from_team=rules_for(pool)['max_from_team'])






