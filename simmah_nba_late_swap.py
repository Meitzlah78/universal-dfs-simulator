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
    for team, players in pool.groupby('Team'):
        times = []
        for value in players.get('Game Start', pd.Series(dtype=str)).dropna().unique():
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
    slate = read_template(template)
    if rules_for(slate['players'])['platform']!=rules_for(pool)['platform'] or set(slate['players']['Player ID']) != set(pool['Player ID']):
        raise ValueError('Late-swap entries must match the current NBA salary slate')
    entries = [r for r in slate['entries'] if r[1] == str(contest_id)]
    size=len(rules_for(pool)['slots'])
    known = set(pool['Player ID'])
    if not entries or any(len(set(r[4:4+size])) != size or not set(r[4:4+size]) <= known for r in entries):
        raise ValueError('Upload current filled entries from FanDuel, with nine valid player IDs per entry')
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


def render_late_swap(st,pool,contest_id,salary_min,diversity):
    rules=rules_for(pool);platform=rules['platform']
    with st.expander('NBA LATE SWAP — fast',expanded=False):
        st.caption(f'For contests that allow late swap. Upload your latest filled {platform} entries. Started games stay frozen in their exact slots. Open slots use current projections and exposure diversity; no full simulation or live ROI calculation. Search is bounded to 10 seconds; unresolved entries stay unchanged.')
        upload=workspace_file_uploader(st,'Current '+platform+' NBA entries',type=['csv'],key='nba_late_swap_upload')
        if upload is None:return
        try:
            data=upload.getvalue();entry_rows(data,contest_id,pool)
            locked=locked_players(pool)
            st.caption(f'{int(locked.sum())} slate players locked by scheduled tipoff. Refresh projections for latest injury and starting-lineup news.')
            import hashlib
            signature=hashlib.sha256(data+pool.to_json().encode()+str(contest_id).encode()+str((salary_min,diversity)).encode()).hexdigest()
            if st.button('FAST LATE SWAP',key='nba_fast_late_swap'):
                started=time.monotonic()
                with st.spinner('Updating unlocked roster spots…'):
                    result=swap_entries(data,contest_id,pool,salary_min=salary_min,diversity=diversity)
                st.session_state['nba_late_swap_result']=(signature,result,time.monotonic()-started)
            saved=st.session_state.get('nba_late_swap_result')
            if saved and saved[0]==signature:
                result=saved[1]
                st.caption(f'Completed in {saved[2]:.2f} seconds. Review unchanged entries before uploading.')
                st.dataframe(result['report'],hide_index=True,width='stretch')
                frame=pd.DataFrame(result['lineups'],columns=rules['slots'])
                from simmah_nba_ui import display_lineups
                st.dataframe(display_lineups(pool,frame),hide_index=True,width='stretch')
                def download_current():
                    try:
                        output=export_swaps(data,contest_id,pool,result)
                        st.download_button('UPLOAD TO '+platform.upper()+' — LATE SWAP CSV',output,'Simmah_NBA_Late_Swap.csv','text/csv',key='nba_late_swap_download',on_click='ignore')
                        st.caption(f'Upload immediately, before the next tipoff. {platform} controls final lock status; scheduled times are used here.')
                    except ValueError as exc:st.error(f'{exc}. Run FAST LATE SWAP again.')
                st.fragment(run_every=5)(download_current)()
        except (ValueError,KeyError) as exc:st.error(str(exc))
