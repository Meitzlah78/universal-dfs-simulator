"""Private FantasyLabs NBA snapshots, matched to the current salary slate."""
import hashlib
import io
import numpy as np
import pandas as pd
from simmah_nba_projections import player_key, team_key
from simmah_nba_rules import rules_for

IMPORTED_COLUMN = 'FantasyLabs Projected Own %'
OPTIMAL_COLUMN = 'FantasyLabs Optimal %'
TEAMS = dict(zip(
    ['Atlanta Hawks','Boston Celtics','Brooklyn Nets','Charlotte Hornets','Chicago Bulls',
     'Cleveland Cavaliers','Dallas Mavericks','Denver Nuggets','Detroit Pistons','Golden State Warriors',
     'Houston Rockets','Indiana Pacers','Los Angeles Clippers','Los Angeles Lakers','Memphis Grizzlies',
     'Miami Heat','Milwaukee Bucks','Minnesota Timberwolves','New Orleans Pelicans','New York Knicks',
     'Oklahoma City Thunder','Orlando Magic','Philadelphia 76ers','Phoenix Suns','Portland Trail Blazers',
     'Sacramento Kings','San Antonio Spurs','Toronto Raptors','Utah Jazz','Washington Wizards'],
    ['ATL','BOS','BKN','CHA','CHI','CLE','DAL','DEN','DET','GS','HOU','IND','LAC','LAL','MEM',
     'MIA','MIL','MIN','NO','NY','OKC','ORL','PHI','PHX','POR','SAC','SA','TOR','UTA','WAS']))


def apply_snapshot(pool, data, platform, day):
    frame = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
    dashboard = set(frame.get('Source', [])) == {'DraftDashboard'}
    if dashboard and 'OWN' in frame and 'Projected Ownership %' not in frame:frame=frame.rename(columns={'OWN':'Projected Ownership %'})
    source = 'DraftDashboard' if dashboard else 'FantasyLabs SimLabs'
    column = 'DraftDashboard Projected Own %' if dashboard else IMPORTED_COLUMN
    required = {'Player','Team','Position','Projected Ownership %','Optimal %','Site','Sport',
                'Slate Date','Source','Source Update ET','Captured UTC'}
    if dashboard:
        required.discard('Optimal %')
    if not required <= set(frame) or frame.empty:
        raise ValueError('Choose the NBA ownership snapshot CSV, not an entries or points file.')
    if set(frame['Site']) != {platform} or set(frame['Sport']) != {'NBA'}:
        raise ValueError('Ownership file belongs to a different site or sport.')
    if set(frame['Slate Date']) != {str(day)}:
        raise ValueError('Ownership file date differs from the current NBA slate.')
    if not dashboard and set(frame['Source']) != {'https://www.fantasylabs.com/nba/simlabs/'}:
        raise ValueError('Expected a FantasyLabs NBA SimLabs snapshot.')
    for col in (['Projected Ownership %'] if dashboard else ['Projected Ownership %','Optimal %']):
        frame[col] = pd.to_numeric(frame[col].str.rstrip('%'), errors='coerce')
        if not (np.isfinite(frame[col]) & frame[col].between(0,100)).all():
            raise ValueError('Ownership and Optimal% must be finite numbers from 0 to 100.')
    expected = 100 * len(rules_for(platform=platform)['slots'])
    total = float(frame['Projected Ownership %'].sum())
    if abs(total-expected) > expected*.01:
        raise ValueError(f'Ownership total {total:.2f}% differs from the required {expected}% by more than 1%.')
    keys = [player_key(r.Player, TEAMS.get(r.Team.strip(), r.Team.strip())) for r in frame.itertuples()]
    if len(set(keys)) != len(keys):
        raise ValueError('Ownership file contains duplicate player/team rows.')
    if {key[1] for key in keys} != {team_key(t) for t in pool['Team']}:
        raise ValueError('Ownership teams differ from the current salary slate. Choose the matching main-slate file.')
    pool_keys = [player_key(r.Name,r.Team) for r in pool.itertuples()]
    if len(set(pool_keys)) != len(pool_keys):
        raise ValueError('Salary slate has ambiguous player/team names; ownership cannot be matched safely.')
    values = dict(zip(keys,frame['Projected Ownership %']))
    result = pool.copy(deep=True)
    result.drop(columns=[IMPORTED_COLUMN, OPTIMAL_COLUMN, 'DraftDashboard Projected Own %'], errors='ignore', inplace=True)
    result[column] = [values.get(k,np.nan) for k in pool_keys]
    applied_fields={}
    if dashboard:
        from simmah_nba_draftdashboard_fields import apply_fields
        result,applied_fields=apply_fields(result,frame,keys,pool_keys)
    if not dashboard:
        optimal = dict(zip(keys,frame['Optimal %']))
        result[OPTIMAL_COLUMN] = [optimal.get(k,np.nan) for k in pool_keys]
    from simmah_nba_ownership import active_players
    missing = active_players(result) & result[column].isna().to_numpy()
    if dashboard and missing.any():
        raise ValueError('DraftDashboard file is missing eligible players: '+', '.join(result.loc[missing,'Name'].astype(str)))
    meta = {'sha256':hashlib.sha256(data).hexdigest(),'site':platform,'date':str(day),
            'source':source,'draftdashboard_fields':applied_fields,'ownership_scope':'main slate' if dashboard else 'uploaded slate','source_update':sorted(set(frame['Source Update ET'])),
            'captured_utc':sorted(set(frame['Captured UTC'])),'raw_total':total,
            'matched_players':sum(k in values for k in pool_keys),
            'missing_eligible_players':result.loc[missing,'Name'].astype(str).tolist(),
            'missing_ownership_policy':'share unreported residual equally',
            'unmatched_source_players':[r.Player for r,k in zip(frame.itertuples(),keys) if k not in set(pool_keys)]}
    result.attrs['fantasylabs_nba_ownership'] = meta
    return result, meta


def render_upload(st, pool, platform, day):
    from simmah_slate_workspaces import workspace_file_uploader
    st.subheader('NBA ownership')
    st.caption('Imported ownership overrides RotoWire ownership. DD PRO and projected MIN also apply when explicitly supplied. DashRank, defensive ranks and usage stay separate context; FPPG is historical. Ownership-only files leave points/minutes unchanged. Optimal% is comparison-only.')
    upload = workspace_file_uploader(st, 'NBA ownership CSV (DraftDashboard or FantasyLabs)', type=['csv'],
        key='nba_ownership_upload_'+platform,
        help='Use the matching DraftKings or FanDuel NBA snapshot for this slate date.')
    if upload is None:
        return pool
    try:
        result, meta = apply_snapshot(pool, upload.getvalue(), platform, day)
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        st.error('NBA ownership upload not applied: '+str(exc))
        st.stop()
        return pool
    st.success(f"{meta['source']} ownership loaded: {meta['matched_players']} matched players · {platform} · {day}")
    if meta.get('draftdashboard_fields'):
        st.caption('DraftDashboard fields loaded: '+', '.join(meta['draftdashboard_fields'])+'. OWN must match this site/date/main slate. Ratings are not added as extra projection boosts.')
    st.caption('Source update: '+', '.join(meta['source_update'])+
               '. This is not a separately verified ownership-update time. Rebuild to apply a changed snapshot.')
    if meta['missing_eligible_players']:
        residual=max(0.,100*len(rules_for(platform=platform)['slots'])-meta['raw_total'])
        st.warning(f"{len(meta['missing_eligible_players'])} eligible players are absent from this snapshot. Their reported ownership stays blank. For field modeling only, the remaining {residual:.2f} percentage points are shared equally among them; these are estimates, not FantasyLabs values.")
        st.caption('Unreported players: '+', '.join(meta['missing_eligible_players']))
    if meta['unmatched_source_players']:
        st.caption('Source players absent from this salary pool: '+', '.join(meta['unmatched_source_players']))
    return result
