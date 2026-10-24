"""Observe external NBA forecasts and grade paired, frozen pregame inputs.

This module never supplies projections, minutes, or weights to the live solver.
"""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import math
import statistics
import pandas as pd
from simmah_nba_projections import player_key, team_key

LINEUPS_URL = 'https://www.lineups.com/nba/nba-player-minutes-per-game/'
PLATFORMS = {'FanDuel': 'fanduelProjection', 'DraftKings': 'draftkingsProjection'}


def stamp(value):
    result = pd.Timestamp(value)
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError('A timezone-aware observation time is required')
    return result.tz_convert('UTC')


def number(value, maximum=None):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) and result >= 0 and (maximum is None or result <= maximum) else None


class _StateParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            attrs = dict(attrs)
            self.inside = attrs.get('type') == 'application/json' and 'data-sdw-ssr-state' in attrs
            self.current = []

    def handle_data(self, data):
        if self.inside:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.inside:
            self.parts.append(''.join(self.current))
            self.inside = False


def parse_lineups(html):
    """Read the public page's own structured data, never its Overall column."""
    parser = _StateParser()
    parser.feed(html)
    candidates = []
    for text in parser.parts:
        value = json.loads(text)
        rows = value.get('data', {}).get('rows') if isinstance(value, dict) else None
        if isinstance(rows, list) and rows and all(isinstance(row, dict) and 'fanduelProjection' in row for row in rows):
            candidates.append(rows)
    if len(candidates) != 1:
        raise ValueError('No unique Lineups projection dataset found; no HTML-column guesses used')
    seen = set()
    records = []
    for row in candidates[0]:
        key = (str(row.get('playerId', '')), str(row.get('gameId', '')))
        if not all(key) or key in seen or not row.get('name') or not row.get('team') or not row.get('opponent'):
            raise ValueError('Missing or duplicated Lineups player/game identity')
        seen.add(key)
        records.append({
            'name': row['name'], 'team': team_key(row['team']), 'opponent': team_key(row['opponent']),
            'source_player_id': key[0], 'source_game_id': key[1], 'minutes': number(row.get('minutes'), 48),
            **{platform: number(row.get(column)) for platform, column in PLATFORMS.items()},
        })
    return records


def freeze_comparison(pool, rw_values, rw_details, lineups, platform, day, *,
                      rotowire_fetched_at, lineups_fetched_at, now=None):
    """Freeze source values, not blended app projections or uploaded overrides.

    Game clocks/dates come from RotoWire. Lineups does not expose an as-of date
    in its page data, so association is explicitly name/team/opponent against
    the dated RotoWire slate at retrieval time, not a provider-ID/date join.
    """
    if platform not in PLATFORMS:
        raise ValueError('Explicit FanDuel or DraftKings scoring required')
    captured = stamp(now or datetime.now(timezone.utc))
    rw_time, lu_time = stamp(rotowire_fetched_at), stamp(lineups_fetched_at)
    if rw_time > captured or lu_time > captured:
        raise ValueError('Source retrieval time cannot be in the future')
    if captured.tz_convert('America/New_York').date().isoformat() != day:
        raise ValueError('Capture must occur on the slate date in Eastern time')
    # A cached old fetch must not masquerade as a fresh pregame forecast.
    if max((captured - rw_time).total_seconds(), (captured - lu_time).total_seconds()) > 1800:
        raise ValueError('Comparison requires source observations no older than 30 minutes')
    buckets = {}
    for row in lineups:
        buckets.setdefault((*player_key(row['name'], row['team']), team_key(row['opponent'])), []).append(row)
    identities = set()
    records = []
    skipped = {'started_or_missing_clock': 0, 'wrong_game_date': 0, 'lineups_unmatched': 0}
    for player in pool.to_dict('records'):
        key = player_key(player['Name'], player['Team'])
        identity = (*key, team_key(player['Opponent']))
        if identity in identities:
            raise ValueError('Ambiguous RotoWire name/team/opponent mapping')
        identities.add(identity)
        details = rw_details.get(key, {})
        try:
            start = pd.Timestamp(details['Game Start'])
            if pd.isna(start):raise ValueError('Missing game start')
            if start.tzinfo is None:start = start.tz_localize('America/New_York')
            start = start.tz_convert('UTC')
        except (ValueError, TypeError, KeyError):
            skipped['started_or_missing_clock'] += 1
            continue
        if start.tz_convert('America/New_York').date().isoformat() != day:
            skipped['wrong_game_date'] += 1
            continue
        if start <= captured:
            skipped['started_or_missing_clock'] += 1
            continue
        matches = buckets.get(identity, [])
        other = matches[0] if len(matches) == 1 else {}
        if not other:skipped['lineups_unmatched'] += 1
        records.append({
            'Name': player['Name'], 'Team': team_key(player['Team']),
            'Opponent': team_key(player['Opponent']), 'Game Start': start.isoformat(),
            'RotoWire Player ID': str(player['Player ID']),
            'RotoWire Points': number(rw_values.get(key)),
            'RotoWire Minutes': number(details.get('Projected Minutes'), 48),
            'Lineups Points': other.get(platform), 'Lineups Minutes': other.get('minutes'),
            'Lineups Player ID': other.get('source_player_id'), 'Lineups Game ID': other.get('source_game_id'),
            'RotoWire Injury': details.get('RotoWire Injury'),
        })
    records.sort(key=lambda row: (row['Game Start'], row['Team'], row['Name']))
    payload = {'schema': 1, 'date': day, 'platform': platform, 'captured_at': captured.isoformat(),
               'rotowire_fetched_at': rw_time.isoformat(), 'lineups_fetched_at': lu_time.isoformat(),
               'players': records, 'skipped': skipped,
               'lineups_date_status': 'No provider as-of date exposed; matched by unique name/team/opponent to same-day RotoWire games at retrieval',
               'purpose': 'Prospective source comparison only; no simulation inputs changed'}
    payload['signature'] = sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return payload


def grade_comparisons(snapshots, actual_rows):
    """Use one last pretip snapshot per player/game/site, and paired coverage.

    Actual rows require date/platform plus FINAL, explicit finite Fantasy Points.
    Absence, a partial box score or a LIVE result never becomes an actual zero.
    """
    latest = {}
    for snapshot in snapshots:
        captured = stamp(snapshot['captured_at'])
        platform, day = snapshot['platform'], snapshot['date']
        if platform not in PLATFORMS:raise ValueError('Unknown scoring platform')
        if captured.tz_convert('America/New_York').date().isoformat() != day:
            raise ValueError('Snapshot date differs from its capture day')
        for row in snapshot['players']:
            start = stamp(row['Game Start'])
            if captured >= start or stamp(snapshot['rotowire_fetched_at']) > captured or stamp(snapshot['lineups_fetched_at']) > captured:
                raise ValueError('Post-tip or inconsistent source observation cannot be graded')
            key = (day, platform, *player_key(row['Name'], row['Team']), team_key(row['Opponent']))
            old = latest.get(key)
            if old is None or captured > old[0]:latest[key] = (captured, row)
            elif captured == old[0] and row != old[1]:raise ValueError('Conflicting snapshots at the same capture time')
    actual = {}
    for row in actual_rows:
        key = (row['date'], row['platform'], *player_key(row['Name'], row['Team']), team_key(row['Opponent']))
        if key in actual:raise ValueError('Ambiguous actual player/date/platform/matchup')
        actual[key] = row
    report = []
    paired = {platform: [] for platform in PLATFORMS}
    coverage = {platform: {'snapshotted': 0, 'final_actuals': 0, 'paired': 0} for platform in PLATFORMS}
    for key, (captured, forecast) in sorted(latest.items()):
        day, platform = key[:2]
        outcome = actual.get(key, {})
        value = number(outcome.get('Fantasy Points')) if outcome.get('Game Status') == 'FINAL' and not outcome.get('Issue') else None
        # Valid NBA fantasy scores may be negative (e.g. turnovers only).
        if outcome.get('Game Status') == 'FINAL' and not outcome.get('Issue'):
            try:
                candidate = float(outcome['Fantasy Points'])
                value = candidate if math.isfinite(candidate) and not isinstance(outcome['Fantasy Points'], bool) else None
            except (ValueError, TypeError, KeyError):value = None
        rw, lu = number(forecast.get('RotoWire Points')), number(forecast.get('Lineups Points'))
        status = 'paired' if value is not None and rw is not None and lu is not None else 'unmatched or incomplete'
        coverage[platform]['snapshotted'] += 1
        coverage[platform]['final_actuals'] += value is not None
        coverage[platform]['paired'] += status == 'paired'
        row = {'date': day, 'platform': platform, **forecast, 'captured_at': captured.isoformat(),
               'Actual Points': value, 'Status': status,
               'RotoWire Error': rw - value if value is not None and rw is not None else None,
               'Lineups Error': lu - value if value is not None and lu is not None else None}
        report.append(row)
        if status == 'paired':paired[platform].append(row)
    summary = []
    for platform, rows in paired.items():
        for source in ('RotoWire', 'Lineups'):
            errors = [row[source + ' Error'] for row in rows]
            summary.append({'platform': platform, 'source': source, 'players': len(errors),
                'slates': len({row['date'] for row in rows}),
                'mae': statistics.mean(map(abs, errors)) if errors else None,
                'rmse': math.sqrt(statistics.mean(x*x for x in errors)) if errors else None,
                'bias': statistics.mean(errors) if errors else None})
    return {'schema': 1, 'summary': summary, 'coverage': coverage, 'players': report,
            'method': 'Last captured pretip forecast per player/game/platform; both sources graded on exactly the same final matched players. No postgame forecast reconstruction.',
            'caveat': 'Lineups provider as-of date is unavailable. Results measure forecasts available at capture, associated by dated RotoWire matchup. ESPN finals can receive stat corrections.'}
