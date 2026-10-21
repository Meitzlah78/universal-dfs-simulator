"""Opt-in, browser-active NBA late-swap preparation; never submits entries."""
import hashlib
import pandas as pd


def refresh_pool(pool, fetch_rw=None, fetch_dff=None):
    from simmah_nba_projections import download_rotowire, download_dff, player_key, positive
    from simmah_nba_rules import rules_for
    platform=rules_for(pool)['platform'];day=pool.attrs.get('slate_date')
    if not day:raise ValueError('Slate date is required for automatic late swap')
    # Require fresh news and both projection requests to succeed. An outage must
    # not turn missing data into zero or silently remove a projection source.
    rw,details,_=(fetch_rw or download_rotowire)(day,pool,platform=platform)
    dff=(fetch_dff or download_dff)(day,pool,platform=platform)
    from simmah_nba_late_swap import locked_players
    locked=locked_players(pool)
    result=pool.copy();result.attrs.update(pool.attrs)
    for number,(idx,row) in enumerate(result.iterrows()):
        if locked[number]:continue  # Never refresh a started game's pregame inputs.
        key=player_key(row['Name'],row['Team']);news=details.get(key)
        if news is None:
            if positive(row['Projection']) is not None:
                raise ValueError('Fresh injury coverage is incomplete; previous export withheld')
            continue  # Unprojected depth players remain excluded, never invented as active.
        tag=str(news.get('RotoWire Injury','')).strip().upper()
        status={'Q':'Questionable','QUES':'Questionable','QUESTIONABLE':'Questionable',
                'D':'Doubtful','DOUBT':'Doubtful','DOUBTFUL':'Doubtful',
                'OUT':'Out','O':'Out','IR':'Out','SUSPENDED':'Out',
                'ACTIVE':'Active','':'Active'}.get(tag)
        if status is None:raise ValueError('Unrecognized injury status; automatic swap paused')
        result.at[idx,'Injury Status']=status
        for col in ('Projected Minutes','Minutes Source','Game Start'):
            if col in news:result.at[idx,col]=news[col]
        if row.get('Projection Source')!='Uploaded CSV':
            values=[positive(source.get(key)) for source in (dff,rw)]
            values=[v for v in values if v is not None]
            result.at[idx,'Projection']=sum(values)/len(values) if values else float('nan')
        result.at[idx,'Eligible']=positive(result.at[idx,'Projection']) is not None and status!='Out'
    return result


def input_signature(pool, locked):
    """Only open-game changes require a new solve; tipoffs also invalidate it."""
    cols=[c for c in ('Player ID','Projection','Injury Status','Projected Minutes','Game Start') if c in pool]
    payload=pool.loc[~locked,cols].sort_values('Player ID').to_json()
    return hashlib.sha256((payload+str(list(map(bool,locked)))).encode()).hexdigest()


def render_auto_swap(st,pool,data,contest_id,salary_min,diversity,markets,contest,
                     saved_build,simulation,actuals,pregame_locked):
    from simmah_nba_late_swap import (entry_rows,locked_players,swap_entries,
        run_simulated_late_swap,revalidate_current_locks,export_swaps)
    from simmah_nba_rules import rules_for
    from simmah_slate_workspaces import workspace_download_button
    from simmah_nba_ui import display_lineups
    rules=rules_for(pool);platform=rules['platform']
    st.caption('Checks every 60 seconds while this slate is open. Automatically prepares swaps using the selected method. Download and upload the CSV yourself. After submitting, upload your latest filled entries here so later checks use the correct locked slots.')
    config=hashlib.sha256(data+str((contest_id,salary_min,diversity,simulation,pregame_locked,markets,
        saved_build.get('identity') if saved_build else None)).encode()+
        (actuals.to_json().encode() if actuals is not None else b'')).hexdigest()
    key='nba_auto_swap_state'
    def monitor():
        state=st.session_state.get(key,{})
        if state.get('config')!=config:state={'config':config}
        try:
            fresh=refresh_pool(pool)
            locks=locked_players(fresh)
            if locks.all():
                st.info('All games have started. Automatic late swap is finished.');return
            entry_rows(data,contest_id,fresh)
            signature=input_signature(fresh,locks)
            if state.get('signature')!=signature:
                with st.spinner('Auto late swap: refreshing affected roster choices…'):
                    if simulation:
                        result=run_simulated_late_swap(data,contest_id,fresh,markets,contest,saved_build,actuals,
                            salary_min=salary_min,diversity=diversity,pregame_locked=pregame_locked)
                    else:result=swap_entries(data,contest_id,fresh,salary_min=salary_min,diversity=diversity)
                state.update(signature=signature,result=result)
            state['checked']=pd.Timestamp.now(tz='America/New_York').strftime('%I:%M:%S %p ET')
            st.session_state[key]=state
            st.caption('Automatic news/projection check: '+state['checked'])
            current=revalidate_current_locks(fresh,state['result'])
            if current['entries_preserved_by_lock_check']:
                st.warning('Tipoff invalidated some proposed swaps; those entries remain exactly as uploaded.')
            if current.get('field_warning'):st.warning(current['field_warning'])
            if current.get('status'):st.caption(current['status'])
            changed=int((current['report']['Changes']>0).sum())
            st.success(f'Updated entries ready: {changed} changed. Review and upload before the next tipoff.')
            st.dataframe(current['report'],hide_index=True,width='stretch')
            st.dataframe(display_lineups(fresh,pd.DataFrame(current['lineups'],columns=rules['slots'])),hide_index=True,width='stretch')
            output=export_swaps(data,contest_id,fresh,current)
            workspace_download_button(st,'EXPORT TO '+platform.upper()+' — AUTO LATE SWAP CSV',
                output,'Simmah_NBA_Auto_Late_Swap.csv','text/csv',key='nba_auto_swap_download',on_click='ignore')
        except Exception as exc:
            # Do not display a stale download after a feed failure or failed solve.
            st.error('Auto late swap paused; no current export prepared: '+str(exc))
            st.caption('The next automatic check will retry. Your uploaded entries have not been changed.')
    st.fragment(run_every=60)(monitor)()
