"""Recover per-event season evidence; never trust scoreboard league season header."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.request


def extract_events(payload, source):
    result = {}
    for event in payload.get('events', []):
        season = event.get('season', {})
        competitions = event.get('competitions', [])
        result[str(event['id'])] = {
            'game_id': str(event['id']), 'kickoff': event.get('date'),
            'season_id': str(season.get('year', '')),
            'season_type_id': season.get('type'), 'season_type_slug': season.get('slug'),
            'season_verified': bool(season.get('year') and season.get('type') and season.get('slug')),
            'season_source': source, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'teams': [c.get('team', {}).get('abbreviation') for c in competitions[0].get('competitors', [])] if competitions else [],
        }
    return result


def run(history_path, out):
    rows = json.loads(Path(history_path).read_text())
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    def fetch(day):
        path = out / (day+'.json')
        if path.exists():
            return json.loads(path.read_text())
        url = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates='+day.replace('-', '')+'&limit=100'
        try:
            payload = json.load(urllib.request.urlopen(url, timeout=20))
            result = {'date': day, 'events': extract_events(payload, url)}
            path.write_text(json.dumps(result, indent=2))
            return result
        except Exception as exc:
            return {'date': day, 'error': type(exc).__name__}
    with ThreadPoolExecutor(max_workers=4) as pool:
        days = list(pool.map(fetch, sorted({r['date'] for r in rows})))
    events = {gid:e for d in days for gid,e in d.get('events', {}).items()}
    audit = []
    for gid in sorted({r['game_id'] for r in rows}):
        group = [r for r in rows if r['game_id'] == gid]
        event = events.get(gid, {})
        # The archive date can be the local game date; do not assert UTC equality.
        matched_teams = {r['key'][1] for r in group} == {{'WSH':'WAS','UTAH':'UTA'}.get(t,t) for t in event.get('teams', [])}
        audit.append(dict(event, game_id=gid, archive_teams_verified=matched_teams,
                          rows=len(group), usable=bool(event.get('season_verified') and matched_teams)))
    (out/'game_metadata.json').write_text(json.dumps(audit, indent=2))
    summary = {'games':len(audit), 'usable_games':sum(r['usable'] for r in audit),
               'season_slugs':{s:sum(r.get('season_type_slug')==s for r in audit) for s in sorted({r.get('season_type_slug','unknown') for r in audit})},
               'request_failures':[d for d in days if 'error' in d]}
    (out/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('history');p.add_argument('out');a=p.parse_args();run(a.history,a.out)
