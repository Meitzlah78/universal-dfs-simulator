from simmah_slate_workspaces import workspace_button
from simmah_slate_workspaces import workspace_download_button
from simmah_slate_workspaces import workspace_file_uploader
"""Bounded NBA late swap: immutable entry slots, current projections, no resimulation."""
import csv
import io
import time
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from simmah_nba_import import read_template
from simmah_nba_rosters import ELIGIBILITY, SLOT_COLUMNS, validate_lineup
from simmah_nba_rules import rules_for


def locked_players(pool, now=None):
    now = pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError('Late swap requires a timezone-aware clock')
    starts = {}
    salary_clocks=pool.attrs.get('salary_game_starts',{})
    for team, players in pool.groupby('Team'):
        times = []
        values=[salary_clocks.get(str(row['Player ID']),row.get('Game Start')) for _,row in players.iterrows()]
        for value in values:
            try:
                if isinstance(value,str) and ':' not in value: continue
                if isinstance(value,str) and ':' not in value: continue
                stamp = pd.Timestamp(value)
                if pd.isna(stamp): continue
                if stamp.tzinfo is None: stamp = stamp.tz_localize('America/New_York')
                times.append(stamp.tz_convert('UTC'))
            except (ValueError, TypeError):
                continue
        if not times or len(set(times)) != 1:
            raise ValueError(f'Confirmed game start time missing or conflicting for {team}; refresh projections before late swap')
        starts[team] = times[0]
    return pool['Team'].map(lambda team: starts[team] <= now).to_numpy(bool)


def entry_rows(template, contest_id, pool):
    slate = read_template(template, game_context_pool=pool)
    if rules_for(slate['players'])['platform']!=rules_for(pool)['platform'] or set(slate['players']['Player ID']) != set(pool['Player ID']):
        raise ValueError('Late-swap entries must match the current NBA salary slate')
    entries = [r for r in slate['entries'] if r[1] == str(contest_id)]
    size=len(rules_for(pool)['slots'])
    known = set(pool['Player ID'])
    if not entries or any(len(set(r[4:4+size])) != size or not set(r[4:4+size]) <= known for r in entries):
        raise ValueError('Upload current filled entries for this site, with valid player IDs in every roster slot')
    return entries


def swap_entries(template, contest_id, pool, *, now=None, salary_min=0, diversity=50, seconds=10):
    """Optimize open slots with HiGHS; preserve failed/time-limited entries unchanged.

    No game outcomes or live ROI are inferred. Started OUT/zero players remain
    locked legally. Missing game clocks block the operation rather than guessing.
    """
    pool = pool.reset_index(drop=True)
    entries = entry_rows(template, contest_id, pool)
    locked = locked_players(pool, now)
    rules=rules_for(pool);size=len(rules['slots'])
    n = len(pool); lookup = {p:i for i,p in enumerate(pool['Player ID'])}
    proj = pd.to_numeric(pool['Projection'],errors='coerce').to_numpy(float)
    active = np.isfinite(proj) & (proj > 0) & ~pool['Injury Status'].str.upper().isin(['OUT','O','IR','SUSPENDED']).to_numpy()
    eligible = np.array([[bool(set(str(p).split('/')) & allowed) for p in pool['Position']] for allowed in rules['eligibility']])
    salary = pool['Salary'].to_numpy(float)
    teams = pool['Team'].unique()
    # Nine slot equalities, player uniqueness, salary, and max-four team rules.
    matrix = [np.repeat(np.eye(size), n, axis=1), np.tile(np.eye(n),(1,size)), np.tile(salary,size)[None,:]]
    matrix += [np.tile((pool['Team']==team).to_numpy(float),size)[None,:] for team in teams]
    if rules['min_games']>1:
        games=pool.apply(lambda r:tuple(sorted((r['Team'],r['Opponent']))),axis=1)
        matrix += [np.tile(games.map(lambda x:x==game).to_numpy(float),size)[None,:] for game in games.unique()]
    a = np.vstack(matrix)
    lower = np.r_[np.ones(size), np.zeros(n), salary_min, np.zeros(len(teams))]
    upper = np.r_[np.ones(size), np.ones(n), rules['salary_cap'], np.full(len(teams),rules['max_from_team'])]
    if rules['min_games']>1:
        lower=np.r_[lower,np.zeros(games.nunique())];upper=np.r_[upper,np.full(games.nunique(),size-1)]
    constraints = [LinearConstraint(a,lower,upper)]
    used = np.zeros(n); output=[]; diagnostics=[]; deadline=time.monotonic()+seconds
    for entry in entries:
        original = np.array([lookup[p] for p in entry[4:4+size]])
        lo=np.zeros((size,n)); hi=(eligible & active[None,:] & ~locked[None,:]).astype(float)
        frozen=locked[original]
        for slot in np.flatnonzero(frozen):
            hi[slot]=0; hi[slot,original[slot]]=1; lo[slot,original[slot]]=1
        remaining=deadline-time.monotonic()
        chosen=original; status='Kept original — search budget exhausted'
        if remaining>0:
            utility=np.nan_to_num(proj,nan=0,posinf=0,neginf=0)-used*float(diversity)/100*2
            result=milp(-np.tile(utility,size),integrality=np.ones(size*n),bounds=Bounds(lo.ravel(),hi.ravel()),
                        constraints=constraints,options={'time_limit':min(.5,remaining),'mip_rel_gap':.005})
            if result.x is not None:
                candidate=result.x.reshape(size,n).argmax(axis=1)
                try:
                    validate_swap(pool, original, candidate, locked, salary_min)
                    chosen=candidate; status='Updated' if not np.array_equal(chosen,original) else 'Unchanged'
                except ValueError:
                    status='Kept original — no valid replacement found'
            else: status='Kept original — no valid replacement found'
        # Prevent introducing duplicate roster sets while respecting exact frozen slots.
        cut=np.zeros(n);cut[chosen]=1
        constraints.append(LinearConstraint(np.tile(cut,size)[None,:],-np.inf,size-1))
        used[chosen]+=1
        output.append([pool.iloc[i]['Player ID'] for i in chosen])
        diagnostics.append({'Entry ID':entry[0],'Status':status,'Locked slots':int(frozen.sum()),
                            'Changes':int((chosen!=original).sum()),'Salary':int(salary[chosen].sum())})
    return {'lineups':output,'report':pd.DataFrame(diagnostics),'original_entries':entries}


def validate_swap(pool, original, candidate, locked, salary_min=0):
    if not np.array_equal(candidate[locked[original]],original[locked[original]]):
        raise ValueError('A started-game player moved from their original slot')
    for slot,idx in enumerate(candidate):
        if locked[idx] and idx != original[slot]: raise ValueError('Cannot add a started-game player')
    # Started players may now be OUT or have no remaining projection.
    check=pool.copy()
    check.loc[locked,'Injury Status']='Active'; check.loc[locked,'Projection']=1.
    rules=rules_for(pool)
    validate_lineup(check,check.iloc[candidate]['Player ID'].tolist(),salary_cap=rules['salary_cap'],max_from_team=rules['max_from_team'],salary_min=salary_min)


def export_swaps(template, contest_id, pool, result, *, now=None):
    entries=entry_rows(template,contest_id,pool)
    rules=rules_for(pool);size=len(rules['slots']);cid_col=2 if rules['platform']=='DraftKings' else 1
    if entries != result['original_entries'] or len(entries)!=len(result['lineups']):
        raise ValueError('Entries changed; run late swap again')
    locked=locked_players(pool,now)
    lookup={p:i for i,p in enumerate(pool['Player ID'])}
    for entry,lineup in zip(entries,result['lineups']):
        original=np.array([lookup[p] for p in entry[4:4+size]])
        candidate=np.array([lookup[p] for p in lineup])
        # Unchanged entries are always preserved, even if already invalid.
        if not np.array_equal(original,candidate):validate_swap(pool,original,candidate,locked)
    rows=list(csv.reader(io.StringIO(template.decode('utf-8-sig'))))
    replacements={entry[0]:lineup for entry,lineup in zip(entries,result['lineups'])}
    for row in rows[1:]:
        if len(row)>=4+size and row[cid_col]==str(contest_id) and row[0] in replacements:row[4:4+size]=replacements[row[0]]
    output=io.StringIO(newline='');csv.writer(output,lineterminator='\r\n').writerows(rows)
    return output.getvalue().encode()


def revalidate_current_locks(pool,result,now=None):
    """Preserve original entries invalidated by tipoff before export.

    Reconcile the visible report and downloaded roster together. Never move a
    newly locked player or insert a started player into a previously open slot.
    """
    locked=locked_players(pool,now);size=len(rules_for(pool)['slots'])
    lookup={str(pid):i for i,pid in enumerate(pool['Player ID'])}
    updated=dict(result);updated['lineups']=[list(row) for row in result['lineups']]
    updated['report']=result['report'].copy()
    unchanged=0
    for number,(entry,lineup) in enumerate(zip(result['original_entries'],result['lineups'])):
        original=np.array([lookup[str(pid)] for pid in entry[4:4+size]])
        candidate=np.array([lookup[str(pid)] for pid in lineup])
        if np.array_equal(original,candidate):continue
        try:validate_swap(pool,original,candidate,locked)
        except ValueError as exc:
            unchanged+=1
            updated['lineups'][number]=[str(pid) for pid in entry[4:4+size]]
            updated['report'].loc[number,'Status']='Kept original — lock check invalidated swap'
            updated['report'].loc[number,'Lock check']=str(exc)
            updated['report'].loc[number,'Changes']=0
            updated['report'].loc[number,'Locked slots']=int(locked[original].sum())
            updated['report'].loc[number,'Salary']=int(pool.iloc[original]['Salary'].sum())
            if 'Conditional Top 1%' in updated['report']:
                updated['report'].loc[number,'Conditional Top 1%']=np.nan
    updated['entries_preserved_by_lock_check']=unchanged
    return updated


def restore_late_swap_clocks(pool, original_template=None, saved_pool=None):
    """Recover missing clocks from this slate's original upload or saved build."""
    from simmah_nba_game_context import restore_saved_game_metadata
    sources=[]
    if pool.attrs.get('salary_game_starts'):
        original_clocks=pool.copy()
        original_clocks['Game Start']=original_clocks['Player ID'].astype(str).map(pool.attrs['salary_game_starts'])
        sources.append(original_clocks)
    if original_template is not None:
        try:sources.append(read_template(original_template,game_context_pool=pool)['players'])
        except ValueError:pass
    if saved_pool is not None:sources.append(saved_pool)
    for source in sources:
        day=source.attrs.get('slate_date') or pool.attrs.get('slate_date')
        if day:pool=restore_saved_game_metadata(pool,source,day)
    return pool


def render_late_swap(st,pool,contest_id,salary_min,diversity,markets=None,contest=None,original_template=None):
    rules=rules_for(pool);platform=rules['platform']
    with st.expander('NBA LATE SWAP — fast',expanded=False):
        st.caption('Current entries support DK pregame, In Progress and Final downloads. Import revision: 2026-10-28.')
        from simmah_nba_swap_recovery import before_swap_csv
        recovered=before_swap_csv(st.session_state.get('nba_late_swap_result'),contest_id,rules['slots'])
        if recovered is not None:
            st.caption('Saved entries from immediately before the last retained late-swap run. Review file only; no simulations are rerun.')
            workspace_download_button(st,'DOWNLOAD BEFORE LATE SWAP',recovered,
                'Simmah_NBA_'+platform+'_Before_Late_Swap_'+str(contest_id)+'.csv','text/csv',
                key='nba_before_late_swap_download_'+str(contest_id),on_click='ignore')
        mode=st.radio('Late-swap method',['Simulate remaining games','Fast projection optimizer'],key='nba_late_swap_method')
        simulation=mode=='Simulate remaining games'
        actuals=None;actual_bytes=b'';pregame_locked=False
        if simulation:
            started_method=st.selectbox('Started-game scoring',['Pregame uncertainty — ignores live scores','Final scores CSV'],key='nba_late_swap_started_method')
            pregame_locked=started_method.startswith('Pregame')
            if pregame_locked:st.warning('Started players remain locked, but their scores are simulated from saved pregame inputs. Live scores, elapsed time and live news are not modeled.')
            actual_file=None if pregame_locked else workspace_file_uploader(st,'Final locked-game fantasy scores CSV',type=['csv'],key='nba_late_swap_actuals_upload',
                help='Player ID, Actual Points, Status. Use exact DK or FD scores and FINAL status. Include explicit zeros; missing scores are never assumed zero.')
            if actual_file is not None:
                try:
                    actual_bytes=actual_file.getvalue()
                    actuals=pd.read_csv(io.BytesIO(actual_bytes),dtype={'Player ID':str})
                except (ValueError,UnicodeError) as exc:
                    st.error('Cannot read final scores: '+str(exc));return
        st.caption(f'For contests that allow late swap. Upload your latest filled {platform} entries. Started games stay frozen in their exact slots. Fast mode uses current projections and exposure diversity, with a 10-second search budget. Sim mode reruns unstarted games; its runtime is longer.')
        upload=workspace_file_uploader(st,'Current '+platform+' NBA entries',type=['csv'],key='nba_late_swap_upload')
        if upload is None:return
        try:
            saved_build=st.session_state.get('nba_build_result')
            pool=restore_late_swap_clocks(pool,original_template,
                saved_build.get('pool') if saved_build else None)
            data=upload.getvalue();current_entries=entry_rows(data,contest_id,pool)
            st.caption(f'{len(current_entries)} {platform} entries loaded for contest {contest_id}.')
            locked=locked_players(pool)
            st.caption(f'{int(locked.sum())} slate players locked by scheduled tipoff. Refresh projections for latest injury and starting-lineup news.')
            import hashlib
            saved_build=st.session_state.get('nba_build_result')
            field_signature=str(saved_build.get('identity','')) if saved_build else ''
            if st.checkbox('AUTO LATE SWAP — prepare updated entries automatically',key='nba_auto_swap_enabled'):
                from simmah_nba_auto_swap import render_auto_swap
                render_auto_swap(st,pool,data,contest_id,salary_min,diversity,markets,contest,
                                 saved_build,simulation,actuals,pregame_locked)
                return
            signature=hashlib.sha256(data+actual_bytes+pool.to_json().encode()+str(contest_id).encode()+str((salary_min,diversity,mode,pregame_locked,markets,field_signature)).encode()).hexdigest()
            if workspace_button(st,'SIMULATE LATE SWAP' if simulation else 'FAST LATE SWAP',key='nba_fast_late_swap'):
                started=time.monotonic()
                with st.spinner('Updating unlocked roster spots…'):
                    if simulation:
                        result=run_simulated_late_swap(data,contest_id,pool,markets,contest,saved_build,actuals,
                            salary_min=salary_min,diversity=diversity,progress=st.write,pregame_locked=pregame_locked)
                    else:
                        result=swap_entries(data,contest_id,pool,salary_min=salary_min,diversity=diversity)
                st.session_state['nba_late_swap_result']=(signature,result,time.monotonic()-started)
            saved=st.session_state.get('nba_late_swap_result')
            if saved and saved[0]==signature:
                result=saved[1]
                st.caption(f'Completed in {saved[2]:.2f} seconds. Review unchanged entries before uploading.')
                if result.get('status'):st.caption(result['status'])
                if result.get('field_warning'):st.warning(result['field_warning'])
                def download_current():
                    try:
                        current=revalidate_current_locks(pool,result)
                        preserved=current['entries_preserved_by_lock_check']
                        if preserved:
                            st.warning(f'{preserved} entry/entries kept exactly as uploaded because the lock check invalidated their swaps. Other valid swaps remain available. Review the report before uploading.')
                        st.dataframe(current['report'],hide_index=True,width='stretch')
                        frame=pd.DataFrame(current['lineups'],columns=rules['slots'])
                        from simmah_nba_ui import display_lineups
                        st.dataframe(display_lineups(pool,frame),hide_index=True,width='stretch')
                        output=export_swaps(data,contest_id,pool,current)
                        st.caption(f"Export ready: {len(current['lineups'])} {platform} entries for contest {contest_id}.")
                        workspace_download_button(st,'EXPORT TO '+platform.upper()+' — LATE SWAP CSV',output,'Simmah_NBA_Late_Swap.csv','text/csv',key='nba_late_swap_download',on_click='ignore',
                            export_checkpoint={'format':platform+' NBA','contest_id':str(contest_id),'kind':'late_swap',
                                'player_pool':pool.copy(deep=True),'original_entries':data,'late_swap':current,
                                'portfolio':frame.copy(deep=True),
                                'lock_check':'Exported CSV uses current lock reconciliation; original and revised rows retained in late_swap payload'})
                        st.caption(f'Upload immediately, before the next tipoff. {platform} controls final lock status; scheduled times are used here.')
                    except ValueError as exc:st.error(f'{exc}. Refresh inputs and run the selected late-swap method again.')
                st.fragment(run_every=5)(download_current)()
        except (ValueError,KeyError) as exc:st.error(str(exc))


def run_simulated_late_swap(template,contest_id,pool,markets,contest,saved,actuals=None,**kwargs):
    """Prepare an unstarted-game engine and remap saved field by exact site IDs."""
    import json
    from pathlib import Path
    from simmah_nba_sim_late_swap import simulate_swap_entries
    from simmah_nba_pregame import PregameEngine,validate_game_reports
    from simmah_nba_engine import EventRates
    from simmah_nba_contests import payout_vector
    from simmah_nba_projections import team_key
    if not saved or str(saved.get('contest_id'))!=str(contest_id) or contest is None:
        raise ValueError('Build this contest first to supply its opponent field and payout schedule')
    original=saved['pool']
    if rules_for(original)['platform']!=rules_for(pool)['platform'] or set(original['Player ID'].astype(str))!=set(pool['Player ID'].astype(str)):
        raise ValueError('Saved opponent field does not match the current salary slate')
    locked=locked_players(pool)
    # Check actuals before expensive simulations, including every field/entry lock.
    lookup={str(pid):i for i,pid in enumerate(pool['Player ID'])}
    remap=np.array([lookup[str(pid)] for pid in original['Player ID']])
    field=dict(saved['result']['field']);field['indices']=remap[np.asarray(field['indices'])]
    pregame_locked=kwargs.get('pregame_locked',False)
    factory_engine=None
    def factory(count,seed,open_indices):
        nonlocal factory_engine
        if factory_engine is None:
            if pregame_locked:
                # Started games retain the saved pregame rotation/projections;
                # only unstarted rows use refreshed news and projections.
                sub=original.set_index(original['Player ID'].astype(str)).loc[pool['Player ID'].astype(str)].copy().reset_index(drop=True)
                for column in pool.columns:
                    if column in sub:sub.loc[~locked,column]=pool.loc[~locked,column].to_numpy()
            else:
                sub=pool.iloc[open_indices].copy().reset_index(drop=True)
            sub.attrs.update(pool.attrs)
            teams=set(sub['Team'].map(team_key))
            lines=[m for m in (markets or []) if set(map(team_key,m['teams']))<=teams]
            model=json.loads((Path(__file__).parent/'data'/'nba_models'/'event-rates-before-2026-04-09.json').read_text())
            day=pool.attrs.get('slate_date')
            if day is None or model['before']>str(day):raise ValueError('Valid slate date and pregame event model required')
            from simmah_nba_role_priors import apply_position_priors
            role_model=json.loads((Path(__file__).parent/'data'/'nba_models'/'position-roles-before-2026-04-09.json').read_text())
            sub=apply_position_priors(sub,role_model,str(day))
            factory_engine=PregameEngine(sub,lines,EventRates(**model['rates']),platform=rules_for(pool)['platform'])
        values=factory_engine(count,seed)
        validate_game_reports(factory_engine.last_report)
        return values
    result=simulate_swap_entries(template,contest_id,pool,factory,field,payout_vector(contest),contest['entry_fee'],
        actuals=actuals,**kwargs)
    if field.get('ownership_fit_warning'):
        result['field_warning']='Conditional ranks use an estimated opponent field: '+field['ownership_fit_warning']
    return result




