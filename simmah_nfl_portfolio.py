"""NFL selector UI boundary: cache, explicit status and recoverable assignments."""
import hashlib,json,logging
import numpy as np
import pandas as pd
from simmah_selector_budget import select_quality_budget,VERSION

LOG=logging.getLogger(__name__)


def selection_key(state,site,mode):
    contest=state.get('selected_dk_contest' if site=='DraftKings' else 'selected_fd_contest') or {}
    return 'nfl_selector_'+site+'_'+mode+'_'+str(contest.get('id') or 'unassigned')


def preserve_existing(state):
    """Called after restoring the slate, before any build invalidation."""
    for site,mode,source in [('DraftKings','Showdown','portfolio_df'),
            ('DraftKings','Classic','classic_contest_entries_df'),
            ('FanDuel','Single Game','fd_assigned_display_single_game'),
            ('FanDuel','Full Roster','fd_full_roster_assigned_portfolio')]:
        value=state.get(source)
        if isinstance(value,pd.DataFrame) and not value.empty:
            state[selection_key(state,site,mode)+'_recovery']=value.copy(deep=True)


def render_status(st,portfolio):
    a=portfolio.attrs
    if a.get('portfolio_selection')!=VERSION:return
    st.caption(f"Portfolio quality budget: at least 95% of the best feasible Top 1% total. "
        f"Quality loss: {100*a['actual_quality_loss']:.2f}%. "
        f"Hard automatic cap: {a['automatic_cap_pct']:g}%. Manual limits stay enforced.")
    if not a.get('diversity_optimal',False):
        st.warning('Diversity search timed out. This portfolio passed the count, quality-budget and exposure checks; minimum concentration was not certified.')


def select_for_app(st,candidates,slots,count,*,controls,diversity,site,mode,previous=None):
    """Return a validated new portfolio or None; caller must stop on None.

    Existing assigned tables are never written here. Recovery copies survive
    invalidation. A timeout preview cannot replace a previous portfolio without
    a user action; first-time valid timeout portfolios can be used immediately.
    """
    state=st.session_state;key=selection_key(state,site,mode)
    if isinstance(previous,pd.DataFrame) and not previous.empty:
        state[key+'_recovery']=previous.copy(deep=True)
    old=state.get(key+'_recovery')
    try:
        if 'Top1' not in candidates:
            raise ValueError('Run CONTEST SIM to obtain Top 1% estimates before selecting an NFL portfolio.')
        # Table sorting is not a selection input. Canonical roster order also
        # makes the cache independent of the user's display ranking choice.
        candidates=candidates.sort_values(slots,kind='stable').reset_index(drop=True)
        sig=hashlib.sha256(pd.util.hash_pandas_object(candidates[slots+['Top1']],index=False).values.tobytes()+
            json.dumps(dict(version=VERSION,count=int(count),controls=controls,diversity=float(diversity)),sort_keys=True,default=str).encode()).hexdigest()
        cached=state.get(key+'_cache')
        if isinstance(cached,dict) and cached.get('signature')==sig:
            portfolio=candidates.iloc[cached['rows']].copy().reset_index(drop=True);portfolio.attrs.update(cached['attrs'])
        else:
            prepared=candidates.copy();prepared['_nfl_selector_row']=np.arange(len(prepared))
            portfolio=select_quality_budget(prepared,slots,int(count),controls=controls,
                automatic_max=100-.4*float(diversity))
            rows=portfolio.pop('_nfl_selector_row').astype(int).tolist()
            portfolio.attrs['portfolio_selection']=VERSION
            portfolio.attrs['research_only']=False
            state[key+'_cache']=dict(signature=sig,rows=rows,attrs=dict(portfolio.attrs))
        timed_out=not portfolio.attrs.get('diversity_optimal',False)
        state[key+'_status']=dict(status='validated diversity timeout' if timed_out else 'completed',**portfolio.attrs)
        render_status(st,portfolio)
        if timed_out:
            LOG.warning('NFL selector timeout: %s',json.dumps(dict(key=key,**portfolio.attrs),default=str))
            if isinstance(old,pd.DataFrame) and not old.empty and state.get(key+'_accepted_timeout')!=sig:
                st.info('Your previously saved lineups are preserved. The new timeout portfolio has not replaced them.')
                with st.expander('Validated timeout portfolio preview',expanded=False):st.dataframe(portfolio,use_container_width=True,hide_index=True)
                if not st.button('Use validated timeout portfolio',key=key+'_accept_'+sig[:12]):
                    if st.button('Retry portfolio selection',key=key+'_retry_'+sig[:12]):
                        state.pop(key+'_cache',None);st.rerun()
                    return None
                state[key+'_previous']=old.copy(deep=True)
            state[key+'_accepted_timeout']=sig
        LOG.info('NFL selector completed: %s',json.dumps(dict(key=key,**portfolio.attrs),default=str))
        return portfolio
    except Exception as exc:
        state[key+'_status']=dict(status='failed; saved lineups preserved',error=str(exc))
        LOG.warning('NFL selector stopped (%s): %s',key,exc)
        st.error('NFL portfolio selection stopped: '+str(exc))
        if isinstance(old,pd.DataFrame) and not old.empty:
            st.info('Previously saved lineups are preserved below. They may be stale for the current inputs; no new assignments were saved.')
            with st.expander('Previously saved lineups',expanded=False):st.dataframe(old,use_container_width=True,hide_index=True)
        return None
