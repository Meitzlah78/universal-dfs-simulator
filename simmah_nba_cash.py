"""Separate equal-payout cash/satellite checks; never replaces tournament entries."""
import hashlib,json
import numpy as np
from simmah_nba_rules import rules_for


def flat_payouts(capacity,paid_places,prize,entry_fee):
    if type(capacity) is not int or not 2<=capacity<=100000:raise ValueError('Use an exact field size from 2 to 100,000')
    if type(paid_places) is not int or not 1<=paid_places<capacity:raise ValueError('Paid places must be fewer than the field size')
    if not np.isfinite(entry_fee) or entry_fee<=0:raise ValueError('Positive entry fee required')
    if not np.isfinite(prize) or prize<=entry_fee:raise ValueError('Prize or ticket face value must exceed the entry fee')
    return np.r_[np.full(paid_places,float(prize)),np.zeros(capacity-paid_places)]


def select_flat_primary(pool,candidates,report):
    """Select one unique primary by expected paid-place share, then mean points."""
    if len(candidates)!=len(report) or report.empty:raise ValueError('Candidate report alignment mismatch')
    columns=['Cash %','Evaluation Mean Points']
    if not set(columns)<=set(report):raise ValueError('Paid-place evaluation is unavailable')
    ranked=report.reset_index(drop=True).copy()
    for j,slot in enumerate(rules_for(pool)['slots']):
        ranked[slot]=pool.iloc[np.asarray(candidates)[:,j]]['Player ID'].astype(str).to_numpy()
    if not np.isfinite(ranked[columns].to_numpy(float)).all():raise ValueError('Nonfinite cash ranking')
    return ranked.sort_values(columns,ascending=False,kind='stable').head(1).reset_index(drop=True)


def render_cash_check(st,pool,engine,ownership,salary_min,excluded,day):
    from simmah_slate_workspaces import workspace_button,workspace_download_button
    from simmah_nba_pipeline import run_pipeline
    from simmah_nba_ui import display_lineups
    platform=rules_for(pool)['platform'];site='DK' if platform=='DraftKings' else 'FD'
    with st.expander('Cash games & satellites — separate build',expanded=False):
        if not st.checkbox('Enable cash / satellite checker',key='nba_cash_enable_'+site):return
        kind=st.selectbox('Contest type',['Cash (50/50 or double-up)','Head-to-head','Satellite (equal tickets)'],key='nba_cash_kind_'+site)
        satellite=kind.startswith('Satellite')
        if kind=='Head-to-head':
            capacity=2;paid=1
            st.caption('One opponent; one winning place.')
        else:
            capacity=int(st.number_input('Exact cash / satellite field size',min_value=2,max_value=100000,value=100,step=1,key='nba_cash_capacity_'+site))
            paid=int(st.number_input('Paid places / tickets awarded',min_value=1,max_value=capacity-1,value=min(45,capacity-1),step=1,key='nba_cash_paid_'+site))
        fee=float(st.number_input('Cash / satellite entry fee ($)',min_value=.01,value=1.,step=.25,key='nba_cash_fee_'+site))
        prize=float(st.number_input('Ticket face value ($)' if satellite else 'Equal prize per paid place ($)',min_value=.01,value=2.,step=.25,key='nba_cash_prize_'+site))
        st.caption('10,000 simulations · 5,000 candidates · 10,000 opponent support target · one primary lineup · diversity 0 · correlation 0. Uses the minimum salary and game/team exclusions above. Tournament exposure caps do not apply to this separate primary lineup.')
        st.warning('Comparison estimate: opponents use current slate ownership, not a separately calibrated cash or satellite field.')
        if satellite:st.caption('Equal-ticket satellites only. Ticket value is face value, not withdrawable cash. Paid-place shares prorate ties; check the contest’s ticket/tie rules.')
        try:payouts=flat_payouts(capacity,paid,prize,fee);issue=None
        except ValueError as exc:payouts=None;issue=str(exc);st.error(issue)
        if engine is None:st.info('Complete the slate projections and rotation inputs before running this check.')
        config=hashlib.sha256((pool.to_json(orient='split')+json.dumps([site,day,kind,capacity,paid,fee,prize,salary_min,list(map(int,excluded))],sort_keys=True)+str(getattr(engine,'identity',''))).encode()).hexdigest()
        key='nba_cash_result_'+site
        if workspace_button(st,'BUILD CASH / SATELLITE CHECK',key='nba_cash_build_'+site,disabled=engine is None or issue is not None):
            try:
                with st.spinner('Building and scoring cash / satellite candidates…'):
                    built=run_pipeline(pool,engine,ownership['weights'],ownership['source'],payouts,fee,1,
                        diversity=0,correlation=0,salary_min=salary_min,ownership_mode=ownership['mode'],
                        excluded_indices=excluded,selection_mode='flat_payout')
                st.session_state[key]={'identity':config,'pool':pool.copy(deep=True),'result':built}
            except Exception as exc:st.error('Cash / satellite build stopped: '+str(exc))
        saved=st.session_state.get(key)
        if not saved:return
        if saved['identity']!=config:
            st.info('Cash / satellite inputs changed. Run the check again to refresh its results.');return
        built=saved['result'];primary=built['portfolio'];saved_pool=saved['pool']
        st.subheader('Satellite primary lineup' if satellite else 'Cash primary lineup')
        show=primary[list(rules_for(saved_pool)['slots'])+['Cash %','Evaluation Mean Points']].copy()
        show=show.rename(columns={'Cash %':'Expected paid-place share %'})
        st.dataframe(display_lineups(saved_pool,show),hide_index=True,width='stretch')
        if not satellite:
            st.caption(f"Estimated return ${primary.iloc[0]['Expected Prize ($)']:.2f} per ${fee:.2f} entry. Estimate depends on the supplied payouts and modeled opponents.")
        if built['field'].get('ownership_fit_warning'):st.warning(built['field']['ownership_fit_warning'])
        report=display_lineups(saved_pool,show)
        for slot in rules_for(saved_pool)['slots']:report[slot+' ID']=primary[slot].astype(str).to_numpy()
        for column,value in [('Platform',platform),('Slate date',day),('Contest type',kind),('Field size',capacity),
                ('Paid places',paid),('Entry fee ($)',fee),('Prize or ticket face value ($)',prize),
                ('Simulations',built.get('simulations_per_set',10000)),('Ranking','Expected paid-place share; ties prorated')]:
            report[column]=value
        workspace_download_button(st,'DOWNLOAD '+site+(' SATELLITE' if satellite else ' CASH')+' LINEUP REPORT',
            report.to_csv(index=False).encode('utf-8-sig'),
            'Simmah_'+site+('_Satellite_' if satellite else '_Cash_')+str(day)+'_Lineup_Report.csv','text/csv',
            key='nba_cash_report_'+site,on_click='ignore')
        st.caption('Review report only. This check does not replace your tournament portfolio or create a DK/FD entries-upload CSV.')
