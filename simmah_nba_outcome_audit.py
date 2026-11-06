"""Read-only postgame checks of frozen NBA forecasts against archived box scores."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
from simmah_nba_projections import player_key, team_key
from simmah_nba_scoring import score_nba

ARCHIVE = Path(__file__).parent / 'data' / 'nba_pbp'


def archive_team(value):
    return team_key({'UTAH': 'UTA', 'WSH': 'WAS'}.get(str(value).upper(), value))


def game_start(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError('Missing game start')
    # Existing provider pools use Eastern wall time (same contract as DK import).
    return stamp.tz_localize('America/New_York') if stamp.tzinfo is None else stamp


def boxscore_actuals(games, platform):
    values = {}
    for game in games:
        events = game.get('events', [])
        if not events or any(int(events[-1][side+'Score']) != int(game[side+'_score']) for side in ('home', 'away')):
            raise ValueError('Archived game final-score ledger is incomplete')
        teams = game['boxscore']['players']
        if len(teams) != 2:
            raise ValueError('Two box-score teams required')
        for t, other in ((teams[0], teams[1]), (teams[1], teams[0])):
            team = archive_team(t['team']['abbreviation'])
            opponent = archive_team(other['team']['abbreviation'])
            for group in t['statistics']:
                for row in group['athletes']:
                    key = (game['date'], *player_key(row['athlete']['displayName'], team), opponent)
                    if key in values:
                        raise ValueError('Ambiguous box-score player identity')
                    if row.get('didNotPlay'):
                        minutes, points = 0., 0.
                    else:
                        stats = dict(zip(group['names'], row.get('stats', [])))
                        if not stats or str(stats.get('MIN','')).strip() in ('', '--'):
                            continue  # Unknown is never a zero.
                        clock = str(stats['MIN']).split(':')
                        minutes = float(clock[0]) + (float(clock[1])/60 if len(clock) == 2 else 0)
                        counts = {name: float(stats[source]) for name, source in
                                  [('points','PTS'),('rebounds','REB'),('assists','AST'),
                                   ('steals','STL'),('blocks','BLK'),('turnovers','TO')]}
                        counts['threes'] = float(stats['3PT'].split('-')[0])
                        if not np.isfinite([minutes, *counts.values()]).all() or min(minutes, *counts.values()) < 0:
                            raise ValueError('Invalid box-score counts')
                        points = float(score_nba(platform, **counts))
                    values[key] = (minutes, points, str(game['event_id']))
    return values


def audit_package(raw, games):
    """Never rerun a forecast using today's inputs or count post-tip captures."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest = json.loads(z.read('manifest.json'))
        if manifest.get('kind') != 'nba_calibration_solver_package':
            raise ValueError('Original NBA build package required')
        def verified(name):
            data = z.read(name)
            if hashlib.sha256(data).hexdigest() != manifest['files'][name]['sha256']:
                raise ValueError('Frozen forecast checksum mismatch: '+name)
            return data
        pool = pd.read_csv(io.BytesIO(verified('inputs/player_pool.csv')), dtype={'Player ID': str})
        with np.load(io.BytesIO(verified('solver/arrays.npz')), allow_pickle=False) as arrays:
            outcomes = {k: arrays[k] for k in arrays.files if k.startswith('outcomes_seed_')}
    if not outcomes:
        raise ValueError('Frozen outcome arrays unavailable')
    capture = pd.Timestamp(manifest['captured_at_utc'])
    if capture.tzinfo is None:
        raise ValueError('Timezone-aware forecast capture required')
    days = set()
    for value in pool['Game Start']:
        try: days.add(game_start(value).tz_convert('America/New_York').date().isoformat())
        except (ValueError, TypeError): pass
    actuals = boxscore_actuals((g for g in games if g['date'] in days), manifest['platform'])
    rows, omitted = [], []
    identities = set()
    for i, row in pool.iterrows():
        if str(row['Eligible']).lower() != 'true' or not float(row['Projection']) > 0:
            continue
        label = {'Player ID': row['Player ID'], 'Name': row['Name'], 'Team': row['Team']}
        try:
            start = game_start(row['Game Start'])
            if capture >= start:
                raise ValueError()
        except (ValueError, TypeError):
            omitted.append(dict(label, reason='Missing start or forecast captured at/after tipoff')); continue
        day = start.tz_convert('America/New_York').date().isoformat()
        key = (day, *player_key(row['Name'], row['Team']), team_key(row['Opponent']))
        if key in identities:
            raise ValueError('Ambiguous frozen player identity')
        identities.add(key)
        if key not in actuals:
            omitted.append(dict(label, reason='No exact completed date/team/opponent/player match')); continue
        minutes, actual, game_id = actuals[key]
        for seed, samples in outcomes.items():
            if samples.ndim != 2 or samples.shape[1] != len(pool) or not len(samples):
                raise ValueError('Frozen outcomes do not align with the player pool')
            x = samples[:, i]
            if not np.isfinite(x).all():
                raise ValueError('Nonfinite frozen outcomes')
            p10, p50, p90, p99 = np.quantile(x, [.1, .5, .9, .99])
            rows.append(dict(label, date=day, game_id=game_id, seed=seed,
                projection=float(row['Projection']), sim_mean=float(x.mean(dtype=np.float64)),
                p10=float(p10), p50=float(p50), p90=float(p90), p99=float(p99), actual=actual,
                projected_minutes=float(row['Projected Minutes']), actual_minutes=minutes))
    frame = pd.DataFrame(rows)
    summaries = []
    if len(frame):
        for seed, group in frame.groupby('seed'):
            summaries.append(dict(seed=seed, players=len(group),
                sim_mae=float(abs(group.sim_mean-group.actual).mean()),
                projection_mae=float(abs(group.projection-group.actual).mean()),
                mean_bias=float((group.sim_mean-group.actual).mean()),
                below_p10=float((group.actual<group.p10).mean()),
                above_p90=float((group.actual>group.p90).mean()),
                above_p99=float((group.actual>group.p99).mean()),
                coverage_80=float(((group.actual>=group.p10)&(group.actual<=group.p90)).mean()),
                minutes_mae=float(abs(group.projected_minutes-group.actual_minutes).mean())))
    return {'contest_id': manifest['contest_id'], 'platform': manifest['platform'],
        'captured_at_utc': capture.isoformat(), 'package_sha256': hashlib.sha256(raw).hexdigest(),
        'status': 'available' if rows else 'pending', 'summaries': summaries,
        'naive_game_start_policy': 'Existing provider wall clocks interpreted as America/New_York, matching NBA import',
        'omitted': omitted, 'rows': rows,
        'scope': 'Pregame player outcomes only; correlated observations and seeds are not independent samples. No automatic model promotion or ROI claim.'}


def archived_games(root=ARCHIVE, days=None):
    for path in archive_paths(root, days):
        with gzip.open(path, 'rt') as stream:
            yield json.load(stream)


def archive_paths(root, days=None):
    return sorted(p for p in Path(root).glob('*/*.json.gz') if days is None or p.parent.name in days)


def render_audit(st, raw, location, root=ARCHIVE):
    """Recheck automatically when archived results or the saved build change."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            pool = pd.read_csv(io.BytesIO(z.read('inputs/player_pool.csv')), usecols=['Game Start'])
        days = {game_start(v).tz_convert('America/New_York').date().isoformat() for v in pool['Game Start'].dropna()}
    except (ValueError, KeyError, zipfile.BadZipFile):
        st.caption('Outcome check requires an original NBA build with saved game start times.'); return
    files = archive_paths(root, days)
    if not files:
        st.caption('Automatic outcome check: waiting for this slate’s completed box scores.'); return
    signature = (hashlib.sha256(raw).hexdigest(), tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files))
    cached = st.session_state.get('_nba_outcome_audit')
    if cached is None or cached[0] != signature:
        try:
            report = audit_package(raw, archived_games(root, days))
        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
            report = {'error': str(exc)}
        st.session_state['_nba_outcome_audit'] = (signature, report)
    else:
        report = cached[1]
    with st.expander('Automatic NBA outcome check', expanded=False):
        if 'error' in report:
            st.warning('Outcome check unavailable: '+report['error']); return
        if not report['summaries']:
            st.caption('Waiting for matching completed box scores. Rechecked automatically when archived results change.'); return
        st.caption('Frozen pregame forecasts versus completed box scores. Expected long-run P10–P90 coverage: 80%. Each seed evaluates the same players; do not add their sample counts.')
        st.dataframe(pd.DataFrame(report['summaries']), hide_index=True)
        if any(s['coverage_80'] < .70 for s in report['summaries']):
            st.warning('Outcome ranges missed more often than expected on this sample. Check minutes uncertainty and tail calibration; this is a diagnostic flag, not proof from one slate.')
        st.caption(str(len(report['omitted']))+' eligible players omitted; unmatched players are not scored as zero. This does not change projections or lineups.')
        from simmah_slate_workspaces import workspace_download_button
        workspace_download_button(st, 'DOWNLOAD NBA OUTCOME CHECK', json.dumps(report, indent=2).encode(),
            'Simmah_NBA_'+report['contest_id']+'_Outcome_Check.json', 'application/json',
            key='nba_outcome_check_'+location, on_click='ignore')
