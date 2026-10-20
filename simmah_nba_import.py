"""FanDuel NBA entry-template import; historical FPPG is never a projection."""
import csv
import io
import time
from decimal import Decimal
import pandas as pd

SLOTS = ('PG', 'SG', 'SF', 'PF', 'C', 'G/F', 'F/C', 'UTIL', 'UTIL')


def read_template(data):
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


def render_setup(st, uploaded_file, tabs, controls):
    try:
        slate = read_template(uploaded_file.getvalue())
    except (ValueError, ArithmeticError) as exc:
        st.error(str(exc))
        return
    pool = slate['players']
    from simmah_nba_projections import slate_date, download_dff, apply_projections
    with tabs[1]:
        if st.button('REFRESH NBA PROJECTIONS', key='nba_projection_refresh'):
            st.session_state.pop('nba_projection_cache', None)
            st.session_state.pop('nba_rotowire_cache', None)
        projection_file = st.file_uploader('Optional NBA projections CSV', type=['csv'], key='nba_projection_upload',
            help='Player ID and Projection columns. Uploaded values override DFF, including zeros that exclude a player.')
    automatic = {}
    try:
        day = slate_date(uploaded_file.name)
        identity = (day, tuple(sorted(zip(pool['Player ID'], pool['Team'], pool['Opponent']))))
        cached = st.session_state.get('nba_projection_cache')
        import time
        if cached and cached['identity'] == identity and time.time()-cached['time'] < 900:
            automatic = cached['values']
        else:
            automatic = download_dff(day, pool)
            st.session_state['nba_projection_cache'] = {'identity':identity, 'time':time.time(), 'values':automatic}
    except Exception as exc:
        with tabs[1]:
            st.warning(f'NBA automatic projections unavailable: {exc}')
    rw_values, rw_details = {}, {}
    try:
        from simmah_nba_projections import download_rotowire
        day = slate_date(uploaded_file.name)
        identity = (day, tuple(sorted(zip(pool['Player ID'], pool['Team'], pool['Opponent']))))
        cached = st.session_state.get('nba_rotowire_cache')
        if cached and cached['identity'] == identity and time.time()-cached['time'] < 900:
            rw_values, rw_details = cached['values'], cached['details']
        else:
            rw_values, rw_details, sid = download_rotowire(day, pool)
            st.session_state['nba_rotowire_cache'] = {'identity':identity, 'time':time.time(),
                'values':rw_values, 'details':rw_details, 'slate_id':sid}
    except Exception as exc:
        with tabs[1]:
            st.warning(f'NBA minutes / RotoWire unavailable: {exc}')
    keys = set(automatic) | set(rw_values)
    combined = {key:sum(source[key] for source in (automatic,rw_values) if key in source)/sum(key in source for source in (automatic,rw_values)) for key in keys}
    try:
        uploaded = pd.read_csv(projection_file, dtype={'Player ID':str}) if projection_file is not None else None
        pool = apply_projections(pool, combined, uploaded)
        for idx, row in pool.iterrows():
            key = (row["Name"].strip().casefold(), row["Team"].upper())
            if pool.at[idx,"Projection Source"] == "DFF":
                pool.at[idx,"Projection Source"] = " + ".join(label for label, source in (("DFF",automatic),("RotoWire",rw_values)) if key in source)
            for col, value in rw_details.get(key, {}).items():
                pool.at[idx,col] = value
            if str(rw_details.get(key,{}).get("RotoWire Injury","")).upper() in {"OUT","O","IR","SUSPENDED"}:
                pool.at[idx,"Injury Status"] = "Out"
                pool.at[idx,"Eligible"] = False
    except ValueError as exc:
        with tabs[1]:
            st.error(str(exc))
        return
    from simmah_nba_markets import extract_markets
    markets = extract_markets(pool)
    slate['markets'] = markets
    slate['players'] = pool
    st.session_state['nba_imported_slate'] = slate
    with tabs[0]:
        st.subheader('FanDuel NBA contests')
        for c in slate['contests']:
            st.write(c['name'])
            st.caption(f"Contest {c['id']} · {c['owned_entries']} entries · ${c['entry_fee']:.2f} each")
        st.write('Games: ' + ' • '.join(sorted(pool['Game'].unique())))
        st.caption('Roster: ' + ', '.join(SLOTS))
        st.subheader('NBA market lines')
        from simmah_nba_markets import implied_scores
        from simmah_nba_projections import team_key
        pairs=sorted({tuple(sorted((team_key(r.Team),team_key(r.Opponent)))) for r in pool.itertuples()})
        by_pair={m['teams']:m for m in markets}
        with st.expander('Edit NBA totals and spreads'):
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
        st.caption('Market calibration is connected to the experimental NBA engine. Live NBA builds remain disabled during validation.')
    with tabs[1]:
        st.subheader('NBA player pool')
        st.caption(f"Positive projections: {pool['Projection'].notna().sum()} / {len(pool)} · Eligible after injuries: {pool['Eligible'].sum()}. Automatic data is cached for up to 15 minutes; refresh runs on app activity.")
        st.caption('Historical FPPG is supplied by FanDuel. It is not a pregame projection. OUT players are ineligible; questionable players remain visible.')
        if 'RotoWire RST % (unverified)' in pool:
            raw_own = pd.to_numeric(pool['RotoWire RST % (unverified)'], errors='coerce')
            st.caption(f'RotoWire raw RST values: {raw_own.notna().sum()} matched; total {raw_own.sum():.1f}%. These are unverified inputs and are not used automatically for opponent ownership.')
        st.dataframe(pool, hide_index=True, use_container_width=True)
        st.write(f"{len(pool)} players · {(pool['Injury Status']=='Out').sum()} Out · {(pool['Injury Status']=='Questionable').sum()} Questionable")
    with tabs[2]:
        st.info('NBA import is ready. NBA projections and simulation are still under development.')
    with tabs[3]:
        st.info('NBA lineups will appear here after the NBA builder is connected.')
    with controls:
        st.caption('FanDuel NBA')
        st.button('BUILD NBA LINEUPS', disabled=True, key='nba_build_pending')
