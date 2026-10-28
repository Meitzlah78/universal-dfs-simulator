"""Capture RotoWire/Lineups before tipoff and grade frozen inputs after finals.

Run from an independent study directory, not the live application's data folder.
"""
import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from simmah_nba_projections import parse_rotowire, team_key
from simmah_nba_projection_comparison import LINEUPS_URL, parse_lineups, freeze_comparison, grade_comparisons
from simmah_nba_live import download_live

BASE = 'https://www.rotowire.com/daily/nba/api/'


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=15) as response:
        raw = response.read()
    return raw, datetime.now(ZoneInfo('America/New_York')).isoformat()


def capture(directory, day):
    html, lu_time = fetch(LINEUPS_URL)
    lineups = parse_lineups(html.decode('utf-8'))
    snapshots, issues = [], []
    for platform, site, mode in [('FanDuel', '2', 'Full Roster'), ('DraftKings', '1', 'Classic')]:
        try:
            listing_raw, _ = fetch(BASE + 'slate-list.php?siteID=' + site)
            listing = json.loads(listing_raw)
            candidates = []
            for slate in listing.get('slates', []):
                games = [listing.get('games', {}).get(str(g)) for g in slate.get('games', [])]
                if slate.get('contestType') == mode and slate.get('startDateOnly') == day and games and all(
                        game and str(game.get('gameDate', ''))[:10] == day for game in games):
                    candidates.append(slate)
            if not candidates:raise ValueError('No same-day full-roster RotoWire slate')
            largest = max(len(s['games']) for s in candidates)
            candidates = [s for s in candidates if len(s['games']) == largest]
            if len(candidates) > 1:
                candidates = [s for s in candidates if s.get('defaultSlate') is True]
            if len(candidates) != 1:raise ValueError('Ambiguous main RotoWire slate')
            slate = candidates[0]
            sid = str(slate['slateID'])
            players_raw, _ = fetch(BASE + 'players.php?slateID=' + sid)
            points_raw, rw_time = fetch(BASE + 'projections.php?slateID=' + sid + '&projSource=RotoWire')
            players, points = json.loads(players_raw), json.loads(points_raw)
            games = [listing['games'][str(g)] for g in slate['games']]
            pairs = {(team_key(g['homeTeamCode']), team_key(g['visitTeamCode'])) for g in games}
            pairs |= {(b, a) for a, b in pairs}
            pool = pd.DataFrame([{
                'Player ID': str(p['slateID']), 'Name': (p.get('firstName', '') + ' ' + p.get('lastName', '')).strip(),
                'Team': team_key(p.get('team', {}).get('abbr', '')),
                'Opponent': team_key(p.get('opponent', {}).get('team', '')),
            } for p in players])
            if pool.empty or any((r.Team, r.Opponent) not in pairs for r in pool.itertuples()):
                raise ValueError('Player feed differs from selected dated slate')
            values, details = parse_rotowire(players, points, day, pool)
            frozen = freeze_comparison(pool, values, details, lineups, platform, day,
                rotowire_fetched_at=rw_time, lineups_fetched_at=lu_time)
            frozen['rotowire_slate_id'] = sid
            frozen['source_sha256'] = {name: sha256(raw).hexdigest() for name, raw in
                [('lineups_html', html), ('rotowire_listing', listing_raw), ('rotowire_players', players_raw), ('rotowire_points', points_raw)]}
            if frozen['players']:snapshots.append(frozen)
            else:issues.append(platform + ': no unstarted, dated games available for capture')
        except (ValueError, KeyError, TypeError, OSError) as exc:
            issues.append(platform + ': ' + str(exc))
    result = {'schema': 1, 'date': day, 'snapshots': snapshots, 'issues': issues,
              'captured_at': datetime.now(ZoneInfo('America/New_York')).isoformat()}
    directory.mkdir(parents=True, exist_ok=True)
    name = datetime.now(ZoneInfo('UTC')).strftime('snapshot-%Y%m%dT%H%M%S%fZ.json')
    path = directory / name
    with path.open('x') as stream:json.dump(result, stream, indent=2, allow_nan=False)
    return {'file': str(path), 'snapshots': len(snapshots),
            'players': sum(len(s['players']) for s in snapshots), 'issues': issues}


def grade(directory):
    snapshots = []
    for path in sorted(directory.glob('snapshot-*.json')):
        snapshots.extend(json.loads(path.read_text())['snapshots'])
    identities = {}
    for snapshot in snapshots:
        key = snapshot['date'], snapshot['platform']
        identities.setdefault(key, set()).update(tuple(sorted((r['Team'], r['Opponent']))) for r in snapshot['players'])
    actuals, issues = [], []
    for (day, platform), pairs in sorted(identities.items()):
        try:
            result = download_live(day, tuple(sorted(pairs)), platform)
            actuals.extend({**row, 'date': day, 'platform': platform} for row in result['rows'])
            issues.extend(platform + ' ' + day + ': ' + issue for issue in result['issues'])
        except (ValueError, KeyError, TypeError, OSError) as exc:
            issues.append(platform + ' ' + day + ': ' + str(exc))
    report = grade_comparisons(snapshots, actuals)
    report['issues'] = issues
    report['graded_at'] = datetime.now(ZoneInfo('America/New_York')).isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'comparison-report.json'
    path.write_text(json.dumps(report, indent=2, allow_nan=False))
    return {'file': str(path), 'summary': report['summary'], 'coverage': report['coverage'], 'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['capture', 'grade'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--date', default=datetime.now(ZoneInfo('America/New_York')).date().isoformat())
    args = parser.parse_args()
    result = capture(args.directory, args.date) if args.action == 'capture' else grade(args.directory)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':main()
