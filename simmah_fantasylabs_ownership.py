"""Private NFL FantasyLabs / DraftDashboard snapshots; no account access."""
import hashlib,io,re,unicodedata
import numpy as np
import pandas as pd

CPT='Projected CPT Own %'
FLEX='Projected Flex Ownership'
OPT_CPT='FantasyLabs CPT Optimal %'
OPT_FLEX='FantasyLabs FLEX Optimal %'


def name_key(value):
    value=unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]','',re.sub(r'\b(jr|sr|ii|iii|iv)\b','',value))


def slate_date(pool):
    dates=set()
    if pool.attrs.get('slate_date'):dates.add(str(pool.attrs['slate_date'])[:10])
    for col in ('Game Info','GameInfo','Game Start','Game Start Time','Kickoff'):
        if col not in pool:continue
        for text in pool[col].dropna().astype(str):
            matches=re.findall(r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}',text)
            dates.update(pd.Timestamp(x).strftime('%Y-%m-%d') for x in matches)
    if len(dates)!=1:raise ValueError('A single confirmed salary-slate date is required for ownership import')
    return dates.pop()


def apply_snapshot(pool,raw,site='DraftKings',mode='single_game',confirmed_undated=False):
    if site not in {'DraftKings','FanDuel'} or mode not in {'single_game','full_roster'}:raise ValueError('Unsupported NFL ownership format')
    special='CPT' if site=='DraftKings' else 'MVP'
    special_col=CPT if special=='CPT' else 'Projected MVP Ownership'
    opt_special=OPT_CPT if special=='CPT' else 'FantasyLabs MVP Optimal %'
    frame=pd.read_csv(io.BytesIO(raw),dtype=str,keep_default_na=False)
    dashboard=set(frame.get('Source',[]))=={'DraftDashboard'}
    source='DraftDashboard' if dashboard else 'FantasyLabs SimLabs'
    required={'Source','Source URL','Captured UTC','Source update label','Site','Slate date','Matchup','Team','Role','Player','Projected Ownership %','Optimal %'}
    if dashboard:
        required.discard('Optimal %')
        frame=frame.rename(columns={'Slate Date':'Slate date','Position':'Role','Source Update ET':'Source update label'})
        required.discard('Matchup')
        required.discard('Source URL')
        if 'Sport' in frame and set(frame['Sport'])!={'NFL'}:raise ValueError('Ownership snapshot must be for NFL')
    if not required<=set(frame):raise ValueError('Upload the NFL DraftDashboard or FantasyLabs ownership snapshot CSV')
    if frame.empty or set(frame['Source'])!={source} or set(frame['Site'])!={site}:
        raise ValueError('Ownership snapshot belongs to a different site/source')
    day=slate_date(pool)
    if set(frame['Slate date'])!={day}:
        if not (set(frame['Slate date'])=={''} and confirmed_undated):raise ValueError('Ownership snapshot date differs from this salary slate or is unconfirmed')
    teams={'Jacksonville Jaguars':'JAX','Baltimore Ravens':'BAL','Arizona Cardinals':'ARI','Atlanta Falcons':'ATL',
        'Buffalo Bills':'BUF','Carolina Panthers':'CAR','Chicago Bears':'CHI','Cincinnati Bengals':'CIN',
        'Cleveland Browns':'CLE','Dallas Cowboys':'DAL','Denver Broncos':'DEN','Detroit Lions':'DET',
        'Green Bay Packers':'GB','Houston Texans':'HOU','Indianapolis Colts':'IND','Kansas City Chiefs':'KC',
        'Las Vegas Raiders':'LV','Los Angeles Chargers':'LAC','Los Angeles Rams':'LAR','Miami Dolphins':'MIA',
        'Minnesota Vikings':'MIN','New England Patriots':'NE','New Orleans Saints':'NO','New York Giants':'NYG',
        'New York Jets':'NYJ','Philadelphia Eagles':'PHI','Pittsburgh Steelers':'PIT','San Francisco 49ers':'SF',
        'Seattle Seahawks':'SEA','Tampa Bay Buccaneers':'TB','Tennessee Titans':'TEN','Washington Commanders':'WAS'}
    # Other games may use their exact site abbreviation in a future snapshot.
    frame['_team']=frame['Team'].map(lambda x:teams.get(x,x)).str.upper().replace({'JAC':'JAX','LA':'LAR','WSH':'WAS'})
    poolteams=pool['Team'].astype(str).str.upper().replace({'JAC':'JAX','LA':'LAR','WSH':'WAS'})
    if (mode=='single_game' and len(set(poolteams))!=2) or set(frame['_team'])!=set(poolteams):
        raise ValueError('Ownership snapshot teams differ from this salary slate')
    frame['Role']=frame['Role'].replace({'AnyFLEX':'FLEX','D':'DST','DEF':'DST'})
    if mode=='single_game' and set(frame['Role'])!={special,'FLEX'}:raise ValueError('Both special-role and FLEX ownership tables are required for this site')
    if mode=='full_roster' and not set(frame['Role'])<={'QB','RB','WR','TE','DST'}:raise ValueError('Full-roster imports require position ownership, not Captain/MVP/FLEX shares')
    for col in (['Projected Ownership %'] if dashboard else ['Projected Ownership %','Optimal %']):
        frame[col]=pd.to_numeric(frame[col].str.rstrip('%'),errors='coerce')
        if not (np.isfinite(frame[col])&frame[col].between(0,100)).all():raise ValueError('Invalid or missing ownership/optimal percentage')
    aliases={'matthewhibner':'matthibner','gregdesrosiers':'gregorydesrosiers'}
    identities=list(zip(poolteams,pool['Name'].map(name_key).replace(aliases)))
    if len(set(identities))!=len(pool):raise ValueError('Ambiguous salary-pool player names')
    index={key:i for i,key in enumerate(identities)}
    # Explicit provider aliases only; no fuzzy matching.
    frame['_key']=frame['Player'].map(name_key).replace(aliases)
    matched=[];unmatched=[]
    for row in frame.to_dict('records'):
        team=row['_team'];key=row['_key'];target=index.get((team,key))
        if target is None and ('defense' in key or row['Role']=='DST'):
            candidates=[i for i,(t,_) in enumerate(identities) if t==team and str(pool.iloc[i].get('Position','')).upper() in {'DST','D','DEF'}]
            if len(candidates)==1:target=candidates[0]
        if target is None:
            unmatched.append(row['Player']+' ('+team+', '+row['Role']+')')
        matched.append(target)
    if unmatched:
        raise ValueError('Ownership players not uniquely matched to salary slate: '+'; '.join(unmatched))
    frame['_index']=matched
    if frame.duplicated(['_index','Role']).any():raise ValueError('Duplicate player/role ownership rows')
    if dashboard:frame['Optimal %']=np.nan
    result=pool.copy(deep=True)
    result.drop(columns=[c for c in result if c.startswith(('FantasyLabs ', 'DraftDashboard ')) and 'Optimal %' in c],inplace=True)
    if mode=='single_game':
        sets={role:set(frame.loc[frame.Role==role,'_index']) for role in (special,'FLEX')}
        if sets[special]!=sets['FLEX']:raise ValueError('Special-role and FLEX player coverage differs')
        sums={role:float(frame.loc[frame.Role==role,'Projected Ownership %'].sum()) for role in (special,'FLEX')}
        if abs(sums[special]-100)>.2 or abs(sums['FLEX']-500)>.2:
            raise ValueError('Role ownership totals differ from 100% special / 500% FLEX beyond display-rounding tolerance')
        for role,col,optcol in [(special,special_col,opt_special),('FLEX',FLEX,OPT_FLEX)]:
            part=frame.loc[frame.Role==role].set_index('_index')
            result[col]=[part['Projected Ownership %'].get(i,np.nan) for i in range(len(pool))]
            if not dashboard:result[optcol]=[part['Optimal %'].get(i,np.nan) for i in range(len(pool))]
        if (result[special_col]+result[FLEX]>100.2).any():raise ValueError('A player cannot exceed 100% combined ownership')
        result['Projected Ownership']=result[special_col]+result[FLEX]
    else:
        if frame['_index'].duplicated().any():raise ValueError('Duplicate full-roster ownership player')
        sums={'overall':float(frame['Projected Ownership %'].sum())}
        if abs(sums['overall']-900)>9.:raise ValueError('NFL full-roster ownership must total approximately 900%')
        part=frame.set_index('_index')
        result['Projected Ownership']=[part['Projected Ownership %'].get(i,np.nan) for i in range(len(pool))]
        if not dashboard:result['FantasyLabs Optimal %']=[part['Optimal %'].get(i,np.nan) for i in range(len(pool))]
    result['Ownership Source']=source+' ownership snapshot (trial)'
    metadata={'source':source,'sha256':hashlib.sha256(raw).hexdigest(),'slate_date':day,'matched_players':frame['_index'].nunique(),'site':site,'format':mode,'special_role':special,
        'raw_totals':sums,'captured_utc':sorted(set(frame['Captured UTC'])),
        'source_update_label':sorted(set(frame['Source update label'])),
        'ownership_updated_utc':None,'mode':'proposal preferences; not exact marginal calibration',
        'missing_pool_players':result.loc[result['Projected Ownership'].isna(),'Name'].astype(str).tolist()}
    result.attrs['fantasylabs_ownership']=metadata
    return result,metadata


def role_preferences(pool):
    fw=pd.to_numeric(pool[FLEX],errors='coerce').to_numpy(float)
    special_col=CPT if pool.attrs.get('fantasylabs_ownership',{}).get('site','DraftKings')=='DraftKings' else 'Projected MVP Ownership'
    cw=pd.to_numeric(pool[special_col],errors='coerce').to_numpy(float)
    if not (np.isfinite(fw)&np.isfinite(cw)&(fw>=0)&(cw>=0)).all():
        raise ValueError('Imported ownership is missing for an eligible opponent player; no fallback or zero fill was used')
    if fw.sum()<=0 or cw.sum()<=0:raise ValueError('Positive ownership mass required for both roles')
    return fw,cw


def full_preferences(pool):
    own=pd.to_numeric(pool['Projected Ownership'],errors='coerce').to_numpy(float)
    if not (np.isfinite(own)&(own>=0)&(own<=100)).all():
        raise ValueError('Imported ownership is missing for an eligible opponent player; no fallback or zero fill was used')
    return own


def field_report(field,pool):
    dk=pool.attrs.get('fantasylabs_ownership',{}).get('site','DraftKings')=='DraftKings'
    special_col=CPT if dk else 'Projected MVP Ownership'
    cp=field['Captain' if dk else 'MVP'].value_counts()/len(field)*100
    fl=field[[('Flex' if dk else 'FLEX')+str(i) for i in range(1,6)]].stack().value_counts()/len(field)*100
    report=pool[['Name',special_col,FLEX]].copy()
    role='CPT' if dk else 'MVP'
    report['Field '+role+' %']=report.Name.map(cp).fillna(0)
    report['Field FLEX %']=report.Name.map(fl).fillna(0)
    report[role+' difference pp']=report['Field '+role+' %']-report[special_col]
    report['FLEX difference pp']=report['Field FLEX %']-report[FLEX]
    return report


def invalidate_field(state,signature,fingerprint,site='DraftKings',mode='single_game'):
    key='fantasylabs_ownership_trial_identity_'+site+'_'+mode
    current=(signature,fingerprint,'role-marginals-v2')
    previous=state.get(key)
    state[key]=current
    if previous==current or (previous is None and fingerprint is None):return False
    keys=('contest_field_df','contest_field_count','contest_field_ready','contest_results_df',
          'portfolio_df','portfolio_count_used','portfolio_metric_used','final_lineups')
    if site=='DraftKings' and mode=='full_roster':
        keys=('classic_contest_field_df','classic_contest_field_ready','classic_contest_comparison_df',
              'classic_contest_entries_df','classic_field_context')
    if site=='FanDuel':
        suffix='single_game' if mode=='single_game' else 'full_roster'
        keys=('fd_contest_field_'+suffix,'fd_contest_field_ready_'+suffix,'fd_lineups_'+suffix,'fd_assigned_display_'+suffix,'fd_assignment_context_'+suffix,'fd_contest_comparison_'+suffix,
              'fd_'+suffix+'_evaluation_context','fd_'+suffix+'_evaluation_engine',
              'fd_'+suffix+'_assigned_portfolio','fd_last_completed_workflow_'+suffix)
        saved=state.get('fd_saved_builds',{})
        if signature in saved:
            saved=dict(saved);saved.pop(signature);state['fd_saved_builds']=saved
    # Preserve old derived outputs for recovery, but never reuse stale rankings.
    state['fantasylabs_ownership_previous_outputs']={k:state[k] for k in keys if k in state}
    for k in keys:state.pop(k,None)
    return True


def render_snapshot(st,pool,site='DraftKings',mode='single_game'):
    from simmah_slate_workspaces import workspace_file_uploader
    label=('DK Showdown' if site=='DraftKings' else 'FD Single Game') if mode=='single_game' else ('DK Classic' if site=='DraftKings' else 'FD Full Roster')
    with st.expander('DraftDashboard / FantasyLabs ownership — '+label+' trial',expanded=False):
        st.caption('Upload the ownership snapshot CSV. Special-role/FLEX shares stay separate where applicable; Optimal% is comparison-only. Point projections and exposure caps stay unchanged.')
        upload=workspace_file_uploader(st,'NFL ownership CSV (DraftDashboard or FantasyLabs)',type=['csv'],key='fantasylabs_ownership_upload_'+site+'_'+mode)
        if upload is None:return pool
        try:
            header=pd.read_csv(io.BytesIO(upload.getvalue()),dtype=str,keep_default_na=False)
            if set(header.get('Source',[]))=={'DraftDashboard'}:header=header.rename(columns={'Slate Date':'Slate date'})
            confirmed=False;current=pool
            try:day=slate_date(pool)
            except ValueError:
                source_days=set(header.get('Slate date',[]))-{''}
                if len(source_days)!=1:
                    selected_day=st.date_input('Salary-slate game date (verify against the salary file)',value=None,key='fantasylabs_salary_day_'+site+'_'+mode)
                    if selected_day is None:
                        st.warning('Select the actual game date; the source calendar date is not proof of the full-roster slate date.');st.stop()
                    day=selected_day.isoformat()
                else:day=source_days.pop()
                if not st.checkbox('Confirm this salary file is for '+day,key='fantasylabs_confirm_day_'+site+'_'+mode):
                    st.warning('Ownership upload is not applied until the salary-slate date is confirmed.');st.stop()
                current=pool.copy();current.attrs['slate_date']=day
            if set(header['Slate date'])=={''}:
                confirmed=st.checkbox('Confirm this ownership table is for the '+day+' salary slate',key='fantasylabs_confirm_undated_'+site+'_'+mode)
                if not confirmed:
                    st.warning('Ownership upload is not applied until the salary-slate date is confirmed.');st.stop()
            result,meta=apply_snapshot(current,upload.getvalue(),site,mode,confirmed_undated=confirmed)
        except (ValueError,KeyError,pd.errors.ParserError) as exc:
            st.error(str(exc));st.stop()
        totals=' · '.join(k+' '+f'{v:.2f}%' for k,v in meta['raw_totals'].items())
        st.success(meta['source']+f" · Matched {meta['matched_players']} players · "+totals)
        st.caption('Captured: '+', '.join(meta['captured_utc'])+' · '+', '.join(meta['source_update_label']))
        st.caption('Refresh ownership for injury news before building. Single-game imports require separate CPT/MVP and FLEX tables; overall ownership cannot supply role shares.')
        columns=[c for c in result if c=='Name' or c.startswith(('Projected ','FantasyLabs '))]
        st.dataframe(result[columns],hide_index=True,width='stretch')
        return result

