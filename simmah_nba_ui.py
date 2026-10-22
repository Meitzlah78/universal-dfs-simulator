from simmah_slate_workspaces import workspace_download_button
"""Experimental NBA workspace wiring; numerical work stays outside Streamlit."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from simmah_nba_contests import saved_contest,payout_vector
from simmah_nba_projections import slate_date
from simmah_nba_pregame import PregameEngine
from simmah_nba_simulation_cache import CachedNBAOutcomes
from simmah_nba_engine import EventRates
from simmah_nba_pipeline import run_pipeline,export_portfolio
from simmah_nba_contest import select_entries
from simmah_nba_rosters import SLOT_COLUMNS
from simmah_nba_rules import rules_for
from simmah_portfolio import portfolio_roi_totals


def input_identity(pool,markets,contest,salary_min,correlation=0,excluded_player_ids=()):
    from simmah_nba_pregame import ROLE_COLUMNS
    columns=[c for c in ['Player ID','Position','Salary','Team','Opponent','Projection','Injury Status',
                         'Projected Minutes','Eligible',*ROLE_COLUMNS,'RotoWire Projected Own %'] if c in pool]
    content={'pool':pool[columns].to_json(orient='split',double_precision=10),'markets':markets,
             'contest':contest,'salary_min':salary_min,'field_model_version':5}
    if correlation:content['build_correlation']=correlation
    if len(excluded_player_ids):content['excluded_player_ids']=sorted(map(str,excluded_player_ids))
    return hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()


def display_lineups(pool,frame,status_pool=None):
    result=frame.copy()
    from simmah_nba_player_display import player_labels
    names=player_labels(pool,status_pool)
    for c in rules_for(pool)['slots']:
        if c in result:result[c]=result[c].astype(str).map(names).fillna(result[c])
    return result



def render_exports(st,upload,cid,pool,built,portfolio,platform,stale,location,status_pool=None):
    st.subheader('Export lineups')
    st.caption('Export the selected portfolio ('+str(len(portfolio))+' lineups), not the full candidate pool.')
    with st.expander('Advanced — reports and frozen inputs'):
        workspace_download_button(st,'DOWNLOAD PORTFOLIO REPORT',display_lineups(pool,portfolio,status_pool).to_csv(index=False).encode(),
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
    workspace_download_button(st,'EXPORT TO '+platform.upper()+' — EDIT ENTRIES CSV',data,
        'Simmah_NBA_'+platform+'_Edit_Entries.csv','text/csv',
        disabled=stale or bool(export_error),key='nba_entries_download' if location=='lineups' else 'nba_entries_download_build',on_click='ignore')
    if stale:st.caption('Inputs changed. Rebuild before downloading a site upload file.')
    if export_error:st.error('Entries export unavailable: '+export_error)
    if platform=='FanDuel':st.link_button('OPEN FANDUEL / EDIT ENTRIES','https://www.fanduel.com/upcoming',key='nba_open_fanduel_'+location)
    elif platform=='DraftKings':
        st.link_button('OPEN DRAFTKINGS / UPLOAD CSV','https://www.draftkings.com/lineup',key='nba_open_draftkings_'+location)
        st.caption('On DraftKings, choose Edit Entries and upload the exported entries CSV.')


def render_workspace(st,slate,upload,tabs,controls,markets):
    pool=slate['players'];rules=rules_for(pool);platform=rules['platform'];slots=rules['slots'];contests={c['id']:c for c in slate['contests']}
    with tabs[0]:
        cid=st.selectbox('NBA contest',list(contests),format_func=lambda x:contests[x]['name'],key='nba_selected_contest')
    selected=contests[cid];count=selected['owned_entries'];error=None;contest=None;engine=None
    from simmah_nba_ownership import field_ownership_inputs
    ownership=field_ownership_inputs(pool)
    try:
        day=slate.get('date') or pool.attrs.get('slate_date') or slate_date(upload.name)
        contest=saved_contest(cid,day,selected['entry_fee'],name=selected['name'],platform=platform)
        if contest is None:
            pending_path=Path(__file__).parent/'data'/'nba_contests'/'pending'/(str(cid)+'.json')
            if pending_path.exists():
                pending=json.loads(pending_path.read_text())
                if pending['id']!=str(cid) or pending['date']!=day or abs(pending['entry_fee']-selected['entry_fee'])>1e-9:
                    raise ValueError('Saved payout schedule differs from uploaded contest')
                with tabs[0]:
                    st.info('Payouts are saved. Enter the exact full contest capacity; the rounded '+pending.get('capacity_display','')+' display cannot determine it.')
                    capacity=st.number_input('Exact contest capacity',min_value=pending['payout_tiers'][-1]['last'],
                        max_value=1000000,value=None,step=1,key='nba_exact_capacity_'+str(cid))
                if capacity is not None:
                    contest=dict(pending,capacity=int(capacity))
                    payout_vector(contest)

        if contest is None:raise ValueError('This NBA contest needs its capacity and payout schedule before builds can run.')
        rates_path=Path(__file__).parent/'data'/'nba_models'/'event-rates-before-2026-04-09.json'
        model=json.loads(rates_path.read_text())
        if model['before']>day:raise ValueError('Historical event baseline follows the selected slate date')
        engine=CachedNBAOutcomes(PregameEngine(pool,markets,EventRates(**model['rates']),platform=platform))
        if engine.missing_markets:
            with tabs[0]:st.warning('Market lines unavailable for: '+', '.join(' vs '.join(pair) for pair in engine.missing_markets)+'. These games use external player projections and historical event rates without Vegas calibration. No totals or spreads are invented.')

    except (ValueError,KeyError,OSError) as exc:error=str(exc)
    with tabs[0]:
        if contest:
            st.caption(f"{contest['capacity']:,} contest places · ${contest['prize_pool']:,.0f} prizes · {count} reserved entries · payouts supplied from your contest")
        st.caption(ownership['source'])
        if ownership['mode']!='projected':st.warning(ownership['status'])
    with controls:
        st.write(f'{count} portfolio entries')
        from simmah_nba_exclusions import game_options,excluded_player_indices
        from simmah_nba_projections import team_key
        _games=list(game_options(pool));_teams=sorted({team_key(team) for team in pool['Team']})
        _game_key='nba_excluded_games_'+platform;_team_key='nba_excluded_teams_'+platform
        for _key,_options in ((_game_key,_games),(_team_key,_teams)):
            if _key in st.session_state:
                _saved_options=st.session_state[_key]
                _valid_options=[value for value in _saved_options if value in _options]
                if _valid_options!=_saved_options:st.session_state[_key]=_valid_options
        excluded_games=st.multiselect('Exclude games',_games,key=_game_key)
        excluded_teams=st.multiselect('Exclude teams',_teams,key=_team_key)
        excluded=excluded_player_indices(pool,excluded_games,excluded_teams)
        if len(excluded):st.caption(f'{len(excluded)} players excluded from your next build. Opponents still use the full slate.')
        salary_min=st.number_input('Minimum salary',min_value=0,max_value=rules['salary_cap'],value=58000 if platform=='FanDuel' else 48000,step=500,key='nba_min_salary' if platform=='FanDuel' else 'nba_min_salary_DraftKings')
        correlation=st.slider('Build correlation',0,100,0,key='nba_build_correlation',
            help='Extra preference for positively correlated player combinations measured from the shared game simulations. 0 = no extra bonus; 100 = strongest bonus. Game simulations remain correlated at every setting.')
        diversity=st.slider('Exposure diversity',0,100,50,key='nba_exposure_diversity')
        metric=st.selectbox('Rank lineups',['Top 1%','Expected ROI (%)','Expected Prize ($)'],key='nba_rank_metric')
        clicked=st.button('BUILD NBA LINEUPS',disabled=bool(error),key='nba_build')
        if error:st.caption(error)
    identity=input_identity(pool,markets,contest,salary_min,correlation,pool.iloc[excluded]['Player ID'])
    saved=st.session_state.get('nba_build_result')
    if clicked:
        with tabs[2]:
            message=st.empty();bar=st.progress(0)
            stages={'Simulating candidate scenarios':.05,'Building independent opponent support':.35,
                    'Scoring independent evaluation scenarios':.65,'Selecting portfolio':.95}
            def progress(text):
                message.write(text)
                if text in stages:bar.progress(stages[text])
            try:
                built=run_pipeline(pool,engine,ownership['weights'],
                    ownership['source'],
                    payout_vector(contest),selected['entry_fee'],count,diversity=diversity,
                    salary_min=salary_min,correlation=correlation,ownership_mode=ownership['mode'],progress=progress,
                    excluded_indices=excluded)
                reports=engine.last_report
                if any((g['calibration'].get('applied',True) and not g['calibration']['within_four_points']) or g['unresolved_tie_fraction']>0 for g in reports):
                    raise ValueError('NBA evaluation failed market calibration or left unresolved overtime; inspect engine validation before exporting')
                saved={'identity':identity,'result':built,'engine_reports':reports,'pool':pool.copy(),'contest_id':cid}
                st.session_state['nba_build_result']=saved
                bar.progress(1.);message.success('NBA build complete')
            except Exception as exc:
                st.error(f'NBA build stopped: {exc}')
    with tabs[3]:
        from simmah_nba_late_swap import render_late_swap
        render_late_swap(st,pool,cid,salary_min,diversity,markets=markets,contest=contest)
    if not saved:
        with tabs[2]:st.info('Ready to build when the contest, projections, rotations and market lines are complete.')
        with tabs[3]:st.info('Your NBA portfolio will appear here after BUILD NBA LINEUPS.')
        return
    stale=saved['identity']!=identity
    built=saved['result'];saved_pool=saved['pool']
    from simmah_nba_player_display import display_pool
    labeled_pool=display_pool(saved_pool,status_pool=pool)
    if built['field'].get('ownership_fit_warning'):
        with tabs[2]:st.warning('Opponent field uses estimated relative popularity because external ownership could not be fitted. '+built['field']['ownership_fit_warning'])
        with tabs[3]:st.warning('ROI uses estimated opponent ownership; the external ownership fit failed.')

    try:
        portfolio=select_entries(saved_pool,built['candidates']['indices'],built['report'],len(built['portfolio']),diversity=diversity,metric=metric)
        built['portfolio']=portfolio
    except ValueError as exc:
        with tabs[3]:st.error(str(exc))
        return
    with tabs[2]:
        if stale:st.info('Inputs or build settings changed. Previous results remain visible; rebuild before exporting.')
        if built.get('timings_seconds'):
            _timing=built['timings_seconds']
            st.caption('Build timing · '+ ' · '.join(label+f" {_timing[key]:.1f}s" for key,label in [('game_scenarios','Game scenarios'),('candidates','Candidates'),('opponent_field','Opponents'),('contest_scoring','Scoring')])+
                f" · {built.get('scenario_cache_hits',0)}/3 scenario sets reused")
        render_exports(st,upload,cid,saved_pool,built,portfolio,platform,stale,'build',status_pool=pool)
        st.subheader('Candidate lineups')
        st.caption(f"{built['candidates']['unique']:,} unique candidates · {built['field']['entries']:,} modeled opponents · {built['field']['unique_rosters']:,} unique opponent rosters. Ownership and ROI are estimates.")
        candidate_rows=built['report'].copy()
        for j,slot in enumerate(slots):candidate_rows[slot]=saved_pool.iloc[built['candidates']['indices'][:,j]]['Player ID'].to_numpy()
        st.dataframe(display_lineups(saved_pool,candidate_rows,status_pool=pool).sort_values(metric,ascending=False),hide_index=True,width="stretch")
        candidate_export=candidate_rows.sort_values(metric,ascending=False).copy()
        candidate_names=saved_pool.set_index('Player ID')['Name']
        for slot in slots:
            candidate_export[slot+' Name']=candidate_export[slot].map(candidate_names)
        workspace_download_button(st,'DOWNLOAD ALL CANDIDATE LINEUPS',
            candidate_export.to_csv(index=False).encode('utf-8-sig'),
            'Simmah_NBA_'+platform.replace(' ','_')+'_All_Candidates.csv','text/csv',
            key='nba_all_candidates_download',on_click='ignore')
        workspace_download_button(st,'DOWNLOAD OPPONENT FIELD',pd.DataFrame(built['field']['indices'],columns=slots).apply(lambda c:c.map(saved_pool['Player ID'].to_dict())).assign(Copies=built['field']['copies']).to_csv(index=False).encode(),
            'Simmah_NBA_Opponent_Field.csv','text/csv',key='nba_field_download',on_click='ignore')
        if st.session_state.get('nba_show_advanced',False):
            with st.expander('NBA engine and ownership report'):
                st.write(saved['engine_reports'])
                st.caption(built['field']['ownership_source'])
                report=pd.DataFrame({'Name':labeled_pool['Name'],'Estimated Field Own %':built['field']['ownership_sampled']})
                if 'RotoWire Projected Own %' in saved_pool:
                    report['RotoWire Projected Own %']=pd.to_numeric(saved_pool['RotoWire Projected Own %'],errors='coerce')
                    report['Field minus RotoWire (pp)']=report['Estimated Field Own %']-report['RotoWire Projected Own %']
                st.dataframe(report,hide_index=True,width="stretch",key="nba_ownership_table",
                             column_config={'Name':st.column_config.TextColumn('Player',pinned=True)})
    with tabs[3]:
        st.subheader('Portfolio ROI — estimated')
        totals=portfolio_roi_totals(portfolio)
        cols=st.columns(4)
        for col,label,value in zip(cols,['Entries','Fees','Estimated winnings','Estimated ROI'],
                                   [str(totals['entries']),f"${totals['fees']:.2f}",f"${totals['winnings']:.2f}",f"{totals['roi']:.1f}%"]):col.metric(label,value)
        st.caption('Experimental model estimates; totals sum marginal lineup estimates against the modeled field.')
        render_exports(st,upload,cid,saved_pool,built,portfolio,platform,stale,'lineups',status_pool=pool)
        st.subheader('My lineups')
        st.dataframe(display_lineups(saved_pool,portfolio,status_pool=pool),hide_index=True,width="stretch")
        exposure=portfolio[list(slots)].stack().value_counts().rename('Lineups')
        exposure=exposure.rename_axis('Player ID').reset_index()
        exposure['Exposure %']=100*exposure['Lineups']/len(portfolio)
        exposure=exposure.merge(labeled_pool[['Player ID','Name','Team','Injury Status']],on='Player ID',how='left')
        st.subheader('Player exposures')
        st.dataframe(exposure[['Name','Team','Injury Status','Lineups','Exposure %']],hide_index=True,width='stretch',key='nba_exposure_table',
                     column_config={'Name':st.column_config.TextColumn('Player',pinned=True)})









