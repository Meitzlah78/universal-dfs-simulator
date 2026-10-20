from simmah_slate_workspaces import workspace_download_button
"""Experimental NBA workspace wiring; numerical work stays outside Streamlit."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from simmah_nba_contests import saved_contest,payout_vector
from simmah_nba_projections import slate_date
from simmah_nba_pregame import PregameEngine
from simmah_nba_engine import EventRates
from simmah_nba_pipeline import run_pipeline,export_portfolio
from simmah_nba_contest import select_entries
from simmah_nba_rosters import SLOT_COLUMNS
from simmah_nba_rules import rules_for
from simmah_portfolio import portfolio_roi_totals


def input_identity(pool,markets,contest,salary_min,correlation=0):
    from simmah_nba_pregame import ROLE_COLUMNS
    columns=[c for c in ['Player ID','Position','Salary','Team','Opponent','Projection','Injury Status',
                         'Projected Minutes',*ROLE_COLUMNS,'RotoWire RST % (unverified)'] if c in pool]
    content={'pool':pool[columns].to_json(orient='split',double_precision=10),'markets':markets,
             'contest':contest,'salary_min':salary_min}
    if correlation:content['build_correlation']=correlation
    return hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()


def display_lineups(pool,frame):
    result=frame.copy()
    names={str(r['Player ID']):str(r['Name'])+({'Questionable':' (Q)','Doubtful':' (D)'}.get(r['Injury Status'],'')) for _,r in pool.iterrows()}
    for c in rules_for(pool)['slots']:
        if c in result:result[c]=result[c].astype(str).map(names).fillna(result[c])
    return result



def render_exports(st,upload,cid,pool,built,portfolio,platform,stale,location):
    st.caption('Export the selected portfolio ('+str(len(portfolio))+' lineups), not the full candidate pool.')
    workspace_download_button(st,'DOWNLOAD PORTFOLIO REPORT',display_lineups(pool,portfolio).to_csv(index=False).encode(),
        'Simmah_NBA_'+platform+'_Portfolio_Report.csv','text/csv',
        key='nba_portfolio_report_'+location,on_click='ignore')
    workspace_download_button(st,'DOWNLOAD BUILD PLAYER POOL',pool.to_csv(index=False).encode('utf-8-sig'),
        'Simmah_NBA_'+platform+'_Build_Player_Pool.csv','text/csv',
        key='nba_build_player_pool_'+location,on_click='ignore',
        help='Frozen player inputs used by this saved build, including RotoWire RST values. Use this file to compare with its opponent field.')
    data=b'';export_error=None
    if not stale:
        try:data=export_portfolio(upload.getvalue(),cid,pool,built)
        except (ValueError,KeyError,IndexError) as exc:export_error=str(exc)
    workspace_download_button(st,'UPLOAD TO '+platform.upper()+' — EDIT ENTRIES CSV',data,
        'Simmah_NBA_'+platform+'_Edit_Entries.csv','text/csv',
        disabled=stale or bool(export_error),key='nba_entries_download' if location=='lineups' else 'nba_entries_download_build',on_click='ignore')
    if stale:st.caption('Inputs changed. Rebuild before downloading a site upload file.')
    if export_error:st.error('Entries export unavailable: '+export_error)
    if platform=='FanDuel':st.link_button('OPEN FANDUEL / EDIT ENTRIES','https://www.fanduel.com/upcoming',key='nba_open_fanduel_'+location)


def render_workspace(st,slate,upload,tabs,controls,markets):
    pool=slate['players'];rules=rules_for(pool);platform=rules['platform'];slots=rules['slots'];contests={c['id']:c for c in slate['contests']}
    with tabs[0]:
        cid=st.selectbox('NBA contest',list(contests),format_func=lambda x:contests[x]['name'],key='nba_selected_contest')
    selected=contests[cid];count=selected['owned_entries'];error=None;contest=None;engine=None
    try:
        day=slate.get('date') or pool.attrs.get('slate_date') or slate_date(upload.name)
        contest=saved_contest(cid,day,selected['entry_fee'])
        if contest is None:raise ValueError('This NBA contest needs its capacity and payout schedule before builds can run.')
        rates_path=Path(__file__).parent/'data'/'nba_models'/'event-rates-before-2026-04-09.json'
        model=json.loads(rates_path.read_text())
        if model['before']>day:raise ValueError('Historical event baseline follows the selected slate date')
        engine=PregameEngine(pool,markets,EventRates(**model['rates']),platform=platform)
        raw=pd.to_numeric(pool.get('RotoWire RST % (unverified)',pd.Series(np.nan,index=pool.index)),errors='coerce')
        if raw[pool['Eligible']].isna().any():raise ValueError('Relative popularity inputs are missing for eligible NBA players')
    except (ValueError,KeyError,OSError) as exc:error=str(exc)
    with tabs[0]:
        if contest:
            st.caption(f"{contest['capacity']:,} contest places · ${contest['prize_pool']:,.0f} prizes · {count} reserved entries · payouts supplied from your contest")
        st.caption('NBA opponent ownership is estimated from legal lineups using raw RotoWire RST as relative popularity. It is not verified projected ownership.')
    with controls:
        st.caption(platform+' NBA · experimental')
        st.write(f'{count} portfolio entries')
        salary_min=st.number_input('Minimum salary',min_value=0,max_value=rules['salary_cap'],value=58000 if platform=='FanDuel' else 48000,step=500,key='nba_min_salary' if platform=='FanDuel' else 'nba_min_salary_DraftKings')
        correlation=st.slider('Build correlation',0,100,0,key='nba_build_correlation',
            help='Extra preference for positively correlated player combinations measured from the shared game simulations. 0 = no extra bonus; 100 = strongest bonus. Game simulations remain correlated at every setting.')
        diversity=st.slider('Exposure diversity',0,100,50,key='nba_exposure_diversity')
        metric=st.selectbox('Rank lineups',['Top 1%','Expected ROI (%)','Expected Prize ($)'],key='nba_rank_metric')
        st.caption('10,000 scenarios per set · 5,000 candidates · up to 10,000 field-support rosters')
        clicked=st.button('BUILD NBA LINEUPS',disabled=bool(error),key='nba_build')
        if error:st.caption(error)
    identity=input_identity(pool,markets,contest,salary_min,correlation)
    saved=st.session_state.get('nba_build_result')
    if clicked:
        with tabs[2]:
            message=st.empty();bar=st.progress(0)
            stages={'Simulating candidate scenarios':.05,'Building independent opponent support':.35,
                    'Scoring independent evaluation scenarios':.65,'Selecting portfolio':.95}
            def progress(text):message.write(text);bar.progress(stages.get(text,0))
            try:
                built=run_pipeline(pool,engine,raw.fillna(0).to_numpy(),
                    'RotoWire raw RST treated as relative popularity; unverified percentages',
                    payout_vector(contest),selected['entry_fee'],count,diversity=diversity,
                    salary_min=salary_min,correlation=correlation,ownership_mode='relative popularity',progress=progress)
                reports=engine.last_report
                if any(not g['calibration']['within_four_points'] or g['unresolved_tie_fraction']>0 for g in reports):
                    raise ValueError('NBA evaluation failed market calibration or left unresolved overtime; inspect engine validation before exporting')
                saved={'identity':identity,'result':built,'engine_reports':reports,'pool':pool.copy(),'contest_id':cid}
                st.session_state['nba_build_result']=saved
                bar.progress(1.);message.success('NBA build complete')
            except Exception as exc:
                st.error(f'NBA build stopped: {exc}')
    with tabs[3]:
        from simmah_nba_late_swap import render_late_swap
        render_late_swap(st,pool,cid,salary_min,diversity)
    if not saved:
        with tabs[2]:st.info('Ready to build when the contest, projections, rotations and market lines are complete.')
        with tabs[3]:st.info('Your NBA portfolio will appear here after BUILD NBA LINEUPS.')
        return
    stale=saved['identity']!=identity
    built=saved['result'];saved_pool=saved['pool']
    try:
        portfolio=select_entries(saved_pool,built['candidates']['indices'],built['report'],len(built['portfolio']),diversity=diversity,metric=metric)
        built['portfolio']=portfolio
    except ValueError as exc:
        with tabs[3]:st.error(str(exc))
        return
    with tabs[2]:
        if stale:st.info('Inputs or build settings changed. Previous results remain visible; rebuild before exporting.')
        st.subheader('Candidate lineups')
        st.caption(f"{built['candidates']['unique']:,} unique candidates · {built['field']['entries']:,} modeled opponents · {built['field']['unique_rosters']:,} unique opponent rosters. Ownership and ROI are estimates.")
        candidate_rows=built['report'].copy()
        for j,slot in enumerate(slots):candidate_rows[slot]=saved_pool.iloc[built['candidates']['indices'][:,j]]['Player ID'].to_numpy()
        st.dataframe(display_lineups(saved_pool,candidate_rows).sort_values(metric,ascending=False),hide_index=True,width="stretch")
        workspace_download_button(st,'DOWNLOAD OPPONENT FIELD',pd.DataFrame(built['field']['indices'],columns=slots).apply(lambda c:c.map(saved_pool['Player ID'].to_dict())).assign(Copies=built['field']['copies']).to_csv(index=False).encode(),
            'Simmah_NBA_Opponent_Field.csv','text/csv',key='nba_field_download',on_click='ignore')
        render_exports(st,upload,cid,saved_pool,built,portfolio,platform,stale,'build')
        with st.expander('NBA engine and ownership report'):
            st.write(saved['engine_reports'])
            st.caption(built['field']['ownership_source'])
            report=pd.DataFrame({'Name':saved_pool['Name'],'Estimated Field Own %':built['field']['ownership_sampled']})
            st.dataframe(report,hide_index=True,width="stretch",key="nba_ownership_table",
                         column_config={'Name':st.column_config.TextColumn('Player',pinned=True)})
    with tabs[3]:
        st.subheader('Portfolio ROI — estimated')
        totals=portfolio_roi_totals(portfolio)
        cols=st.columns(4)
        for col,label,value in zip(cols,['Entries','Fees','Estimated winnings','Estimated ROI'],
                                   [str(totals['entries']),f"${totals['fees']:.2f}",f"${totals['winnings']:.2f}",f"{totals['roi']:.1f}%"]):col.metric(label,value)
        st.caption('Experimental model estimates; totals sum marginal lineup estimates against the modeled field.')
        st.subheader('My lineups')
        st.dataframe(display_lineups(saved_pool,portfolio),hide_index=True,width="stretch")
        render_exports(st,upload,cid,saved_pool,built,portfolio,platform,stale,'lineups')
        exposure=portfolio[list(slots)].stack().value_counts().rename('Lineups')
        exposure=exposure.rename_axis('Player ID').reset_index()
        exposure['Exposure %']=100*exposure['Lineups']/len(portfolio)
        exposure=exposure.merge(saved_pool[['Player ID','Name','Team','Injury Status']],on='Player ID',how='left')
        st.subheader('Player exposures')
        st.dataframe(exposure[['Name','Team','Injury Status','Lineups','Exposure %']],hide_index=True,width='stretch',key='nba_exposure_table',
                     column_config={'Name':st.column_config.TextColumn('Player',pinned=True)})
