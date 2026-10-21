from simmah_slate_workspaces import workspace_file_uploader, workspace_download_button
"""FanDuel NBA entry-template import; historical FPPG is never a projection."""
import csv
import io
import time
from decimal import Decimal
import pandas as pd

SLOTS = ('PG', 'SG', 'SF', 'PF', 'C', 'G/F', 'F/C', 'UTIL', 'UTIL')


def read_template(data):
    if data.decode('utf-8-sig').startswith('Entry ID,Contest Name,Contest ID,Entry Fee,PG,SG,SF,PF,C,G,F,UTIL'):
        from simmah_nba_dk_import import read_draftkings
        return read_draftkings(data)
    rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
    if not rows or tuple(rows[0][4:13]) != SLOTS or rows[0][:2] != ['entry_id', 'contest_id']:
        raise ValueError('Expected a FanDuel NBA nine-slot entries template')
    entries = [r[:13] for r in rows[1:] if len(r) >= 13 and r[0].isdigit() and r[1]]
    if not entries or len({r[0] for r in entries}) != len(entries):
        raise ValueError('Entry IDs must be present and unique')
    start = next((i for i, r in enumerate(rows) if 'Id' in r and 'Nickname' in r and 'Salary' in r), None)
    if start is None:
        raise ValueError('The player/salary table is missing')
    header = rows[start]
    def cell(row, name):
        i = header.index(name)
        return row[i].strip() if i < len(row) else ''
    players = []
    for row in rows[start+1:]:
        pid = cell(row, 'Id')
        if not pid:
            continue
        name = cell(row, 'Nickname')
        salary = Decimal(cell(row, 'Salary'))
        pos = cell(row, 'Position')
        if not name or salary <= 0 or salary != int(salary) or not set(pos.split('/')) <= {'PG','SG','SF','PF','C'}:
            raise ValueError('Invalid NBA player name, salary or position')
        injury = cell(row, 'Injury Indicator').upper()
        players.append({'Player ID':pid, 'Name':name, 'Position':pos, 'Salary':int(salary),
            'Team':cell(row,'Team'), 'Opponent':cell(row,'Opponent'), 'Game':cell(row,'Game'),
            'Injury Status':{'O':'Out','Q':'Questionable','D':'Doubtful'}.get(injury,injury or 'Active'),
            'Injury Details':cell(row,'Injury Details'),
            'Historical FPPG':float(cell(row,'FPPG') or 0), 'Projection':None})
    pool = pd.DataFrame(players)
    if pool.empty or pool['Player ID'].duplicated().any():
        raise ValueError('Player IDs must be present and unique')
    prefixes = {p.split('-')[0] for p in pool['Player ID']}
    if any(r[1].split('-')[0] not in prefixes for r in entries):
        raise ValueError('Entry contest and salary slate IDs do not match')
    contests = []
    for cid in dict.fromkeys(r[1] for r in entries):
        owned = [r for r in entries if r[1] == cid]
        if len({(r[2],r[3]) for r in owned}) != 1:
            raise ValueError('Conflicting contest metadata')
        contests.append({'id':cid, 'name':owned[0][2], 'entry_fee':float(Decimal(owned[0][3])), 'owned_entries':len(owned)})
    return {'entries':entries, 'players':pool, 'contests':contests, 'slots':SLOTS}


def render_setup(st, uploaded_file, tabs, controls, game_header=None):
    try:
        slate = read_template(uploaded_file.getvalue())
    except (ValueError, ArithmeticError) as exc:
        st.error(str(exc))
        return
    pool = slate['players']
    platform = slate.get('platform','FanDuel')
    from simmah_nba_slate_date import resolve_slate_date
    try:
        day = resolve_slate_date(slate,uploaded_file.name)
    except (ValueError,KeyError,OSError) as exc:
        with tabs[0]:st.error('NBA slate date could not be resolved: '+str(exc))
        return
    if day is None:
        with tabs[0]:
            st.info('This file has no dated game information or matching saved contest. Select its slate date to load projections.')
            chosen = st.date_input('NBA slate date',value=None,key='nba_explicit_slate_date_'+platform)
        if chosen is None:
            with controls:st.caption('Choose the NBA slate date in Contests before building.')
            return
        day = chosen.isoformat()
    slate['date'] = day
    pool.attrs['slate_date'] = day
    from simmah_nba_projections import slate_date, download_dff, apply_projections, player_key, read_projection_upload, EntriesInProjectionUpload
    _force_refresh=st.session_state.pop('refresh_projections_requested',False)
    if _force_refresh:
        from simmah_nba_confirmed import download_lineup_page_result
        st.cache_data(ttl=60,show_spinner=False,max_entries=8)(download_lineup_page_result).clear()
        from simmah_nba_game_context import download_game_context_result
        st.cache_data(ttl=60,show_spinner=False,max_entries=8)(download_game_context_result).clear()
        st.session_state['nba_lineup_refresh_requested']=True
        st.session_state['projection_updates_found']=False
        st.session_state['injury_updates_found']=False
    with tabs[1]:
        projection_file = workspace_file_uploader(st,'Optional NBA projections CSV', type=['csv'], key='nba_projection_upload_'+platform,
            help='Player ID and Projection columns. Uploaded values override DFF, including zeros that exclude a player.')
    from simmah_nba_source_cache import load_sources
    from simmah_nba_projections import download_rotowire
    identity=(platform,day,tuple(sorted(zip(pool['Player ID'],pool['Team'],pool['Opponent']))),'reserve-metadata-v7')
    def _load_dff():
        return {'values':download_dff(day,pool,platform=platform)}
    def _load_rw():
        values,details,sid=download_rotowire(day,pool,platform=platform)
        return {'values':values,'details':details,'slate_id':sid}
    with st.spinner('Checking NBA projection sources (up to 12 seconds)…'):
        _sources=load_sources(st.session_state,identity,
            {'nba_projection_cache':_load_dff,'nba_rotowire_cache':_load_rw},force=_force_refresh)
    automatic=_sources['nba_projection_cache'].get('values',{})
    _rw=_sources['nba_rotowire_cache']
    rw_values,rw_details=_rw.get('values',{}),_rw.get('details',{})
    for _key,_label in [('nba_projection_cache','NBA automatic projections'),('nba_rotowire_cache','NBA minutes / RotoWire')]:
        _source=_sources[_key]
        if _source.get('error'):
            with tabs[1]:
                _fallback=' Last successful data retained; it may be stale.' if 'time' in _source else ''
                st.warning(_label+' unavailable: '+_source['error']+_fallback+' Automatic retry pauses for up to 60 seconds; REFRESH retries immediately.')
    if rw_details and not _rw.get('error') and st.session_state.pop('nba_lineup_refresh_requested',False):
        from simmah_nba_lineups import acknowledge_lineup_refresh
        acknowledge_lineup_refresh(st.session_state)
    keys = set(automatic) | set(rw_values)
    combined = {key:sum(source[key] for source in (automatic,rw_values) if key in source)/sum(key in source for source in (automatic,rw_values)) for key in keys}
    uploaded = None
    if projection_file is not None:
        try:
            uploaded = read_projection_upload(projection_file.getvalue())
        except EntriesInProjectionUpload as exc:
            with tabs[1]:st.warning(str(exc))
            st.session_state.get('_slate_restored_uploads',{}).pop('nba_projection_upload_'+platform,None)
        except ValueError as exc:
            with tabs[1]:st.error(str(exc))
            return
    try:
        pool = apply_projections(pool, combined, uploaded)
        for idx, row in pool.iterrows():
            key = player_key(row["Name"], row["Team"])
            if pool.at[idx,"Projection Source"] == "DFF":
                pool.at[idx,"Projection Source"] = " + ".join(label for label, source in (("DFF",automatic),("RotoWire",rw_values)) if key in source)
            for col, value in rw_details.get(key, {}).items():
                pool.at[idx,col] = value
            injury=str(rw_details.get(key,{}).get("RotoWire Injury","")).upper()
            if injury in {'Q','QUES','QUESTIONABLE'}:pool.at[idx,'Injury Status']='Questionable'
            elif injury in {'D','DOUBT','DOUBTFUL'}:pool.at[idx,'Injury Status']='Doubtful'
            if str(rw_details.get(key,{}).get("RotoWire Injury","")).upper() in {"OUT","O","IR","SUSPENDED"}:
                pool.at[idx,"Injury Status"] = "Out"
                pool.at[idx,"Eligible"] = False
    except ValueError as exc:
        with tabs[1]:
            st.error(str(exc))
        return
    from simmah_nba_confirmed import current_confirmed_pool
    from simmah_nba_projections import team_key
    _status_pairs=tuple(sorted({(team_key(r.Team),team_key(r.Opponent)) for r in pool.itertuples()}))
    pool,_shared_status=current_confirmed_pool(st,pool,day,_status_pairs)
    if _shared_status['stale']:
        with tabs[1]:st.caption('Starting-lineup feed unavailable. Previous same-slate statuses are labeled Last confirmed / Last expected.')
    from simmah_nba_markets import extract_markets
    try:
        import json
        from pathlib import Path
        from simmah_nba_role_priors import apply_position_priors
        model_path=Path(__file__).parent/'data'/'nba_models'/'position-roles-before-2026-04-09.json'
        pool=apply_position_priors(pool,json.loads(model_path.read_text()),day)
    except (ValueError, OSError) as exc:
        with tabs[1]:
            st.warning(f'NBA historical role priors unavailable: {exc}')
    _minutes=pd.to_numeric(pool.get('Projected Minutes',pd.Series(index=pool.index,dtype=float)),errors='coerce')
    _projection=pd.to_numeric(pool['Projection'],errors='coerce')
    _zero_minutes=_minutes.eq(0)
    pool.loc[_zero_minutes,'Eligible']=False
    _missing_minutes=(_projection>0) & ~_zero_minutes & ~pool['Injury Status'].astype(str).str.upper().isin(['OUT','O','IR','SUSPENDED']) & ~_minutes.between(0,48,inclusive='right')
    if _missing_minutes.any():
        with tabs[1]:
            st.warning(f'{int(_missing_minutes.sum())} projected NBA player(s) have unavailable or invalid minutes. The slate can be viewed, but simulation builds need complete projected rotations. Refresh projections to retry the minutes provider; missing minutes are not treated as zero.')
    from simmah_nba_game_context import download_game_context_result,apply_game_context,has_game_context
    if not has_game_context(pool):
        try:
            _game_pairs=tuple(sorted({tuple(sorted((team_key(r.Team),team_key(r.Opponent)))) for r in pool.itertuples()}))
            _context_result=st.cache_data(ttl=60,show_spinner=False,max_entries=8)(download_game_context_result)(day,_game_pairs)
            if _context_result.get('error'):raise ValueError(_context_result['error'])
            pool=apply_game_context(pool,_context_result['values'])
        except (ValueError,OSError,KeyError,TypeError):
            with tabs[1]:st.caption('NBA game times / market feed unavailable; existing salary-file and projection metadata retained.')
    markets = extract_markets(pool)
    slate['markets'] = markets
    slate['players'] = pool
    st.session_state['nba_imported_slate'] = slate
    with tabs[0]:
        st.subheader(platform+' NBA contests')
        for c in slate['contests']:
            st.write(c['name'])
            st.caption(f"Contest {c['id']} · {c['owned_entries']} entries · ${c['entry_fee']:.2f} each")
        with st.expander('Market lines — view or edit',expanded=False):
            from simmah_nba_markets import implied_scores
            from simmah_nba_projections import team_key
            pairs=sorted({tuple(sorted((team_key(r.Team),team_key(r.Opponent)))) for r in pool.itertuples()})
            by_pair={m['teams']:m for m in markets}
            for pair in pairs:
                a,b=pair
                current=by_pair.get(pair,{})
                key='nba_market_'+str(day if 'day' in locals() else uploaded_file.name)+'_'+a+'_'+b
                if st.checkbox(f'Use manual lines: {a} vs {b}',key=key+'_manual'):
                    total=st.number_input(f'{a} vs {b} total',min_value=101.,max_value=399.,value=float(current.get('total',230.)),step=.5,key=key+'_total')
                    spread=st.number_input(f'{a} spread (negative = favored)',min_value=-99.,max_value=99.,value=float(current.get('team_0_spread',0.)),step=.5,key=key+'_spread')
                    points=implied_scores(total,spread)
                    by_pair[pair]={'teams':pair,'total':total,'team_0_spread':spread,'implied_points':points,'source':'Manual override'}
            markets=list(by_pair.values())
            slate['markets']=markets
            st.session_state['nba_game_markets']=markets
            for market in markets:
                a, b = market['teams']
                x, y = market['implied_points']
                st.write(f"{a} vs {b} · Total {market['total']:g} · {a} {market['team_0_spread']:+g} · Implied {a} {x:g}, {b} {y:g}")
                st.caption(market['source'] + (' · refreshed with NBA projections; cached up to 15 minutes' if market['source'] != 'Manual override' else ''))
            if not markets:
                st.info('No complete, consistent market lines are available for this NBA slate.')
    if game_header is not None:
        from simmah_nba_lineups import render_live_strip
        source_cache=st.session_state.get('nba_rotowire_cache',{})
        with game_header:
            render_live_strip(st,pool,markets,source_cache.get('slate_id') if rw_details else None,
                              day,source_cache.get('time') if rw_details else None)
    with tabs[1]:
        from simmah_nba_news import render_underdog_news
        render_underdog_news(st)
        from simmah_nba_live import render_live_points
        render_live_points(st,pool,day,platform)
        from simmah_nba_minutes_validation import render_minutes_snapshots
        _advanced=st.checkbox('Show advanced reports and validation',key='nba_show_advanced')
        render_minutes_snapshots(st,pool,platform,show_controls=_advanced)
        st.subheader('NBA player pool')
        st.caption(f"Positive projections: {pool['Projection'].notna().sum()} / {len(pool)} · Eligible after injuries: {pool['Eligible'].sum()}. Automatic data is cached for up to 15 minutes; refresh runs on app activity.")
        from simmah_nba_ownership import field_ownership_inputs
        ownership_check=field_ownership_inputs(pool)
        st.caption(ownership_check['source'])
        if ownership_check['mode']!='projected':st.warning(ownership_check['status'])
        leading_columns = ['Name', 'Starter Confirmed', 'Injury Status', 'Position', 'Team',
                           'Opponent', 'Salary', 'Projection', 'Projection Source',
                           'RotoWire Projected Own %', 'Projected Minutes', 'Minutes Source']
        column_order = [column for column in leading_columns if column in pool.columns]
        column_order += [column for column in pool.columns if column not in leading_columns]
        from simmah_nba_player_display import display_pool
        st.caption("✅ = confirmed starter; Q/D injury tags remain visible.")
        st.dataframe(display_pool(pool), hide_index=True, width="stretch", key="nba_player_pool_table",
                     column_order=column_order,
                     column_config={'Name': st.column_config.TextColumn('Player', pinned=True)})
        workspace_download_button(st,'DOWNLOAD PLAYER POOL',
            pool[column_order].to_csv(index=False).encode('utf-8-sig'),
            'Simmah_NBA_'+platform+'_Player_Pool.csv','text/csv',
            key='nba_player_pool_download',on_click='ignore')
        st.write(f"{len(pool)} players · {(pool['Injury Status']=='Out').sum()} Out · {(pool['Injury Status']=='Questionable').sum()} Questionable")
    from simmah_nba_ui import render_workspace
    render_workspace(st,slate,uploaded_file,tabs,controls,markets)





