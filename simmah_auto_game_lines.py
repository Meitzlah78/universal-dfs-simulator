"""Exact-match pregame spreads/totals from ESPN's public scoreboard."""
import json
import math
import re
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


def team_key(value):
    value = str(value).strip().upper()
    return {'WSH':'WAS','JAC':'JAX','LA':'LAR'}.get(value,value)


def parse_scoreboard(payload, games, dates, now=None):
    now = now or datetime.now(timezone.utc)
    wanted = {tuple(team_key(t) for t in game.split(' @ ')):game for game in games}
    found = {}
    for event in payload.get('events', []):
        for competition in event.get('competitions', []):
            status = competition.get('status', event.get('status', {})).get('type', {})
            if status.get('state') != 'pre' or status.get('completed'):
                continue
            try:
                kickoff = datetime.fromisoformat(event['date'].replace('Z','+00:00'))
                if kickoff <= now or kickoff.astimezone(ZoneInfo('America/New_York')).date().isoformat() not in dates:
                    continue
                sides = {row['homeAway']:team_key(row['team']['abbreviation']) for row in competition['competitors']}
                pair = (sides['away'], sides['home'])
            except (KeyError, TypeError, ValueError):
                continue
            if pair not in wanted:
                continue
            for odds in competition.get('odds', []):
                try:
                    total = float(odds['overUnder'])
                    # Details identifies the favored team explicitly; never assume
                    # a numeric spread belongs to the home side.
                    details = str(odds.get('details', '')).strip().upper()
                    match = re.fullmatch(r'([A-Z]{2,3})\s+([+-]?\d+(?:\.\d+)?)', details)
                    if match:
                        favored, value = team_key(match[1]), float(match[2])
                        if favored not in pair:
                            continue
                        spread = value if favored == pair[1] else -value
                    elif float(odds.get('spread', float('nan'))) == 0:
                        spread = 0.
                    elif isinstance(odds.get('homeTeamOdds', {}).get('favorite'), bool):
                        spread = abs(float(odds['spread'])) * (-1 if odds['homeTeamOdds']['favorite'] else 1)
                    else:
                        continue
                    if not math.isfinite(total) or not math.isfinite(spread) or not 0 < total <= 100 or abs(spread) >= total:
                        continue
                    record = {'total':total, 'home_spread':spread,
                        'source':'ESPN / ' + str(odds.get('provider', {}).get('name') or 'sportsbook'),
                        'fetched_at':now.isoformat(), 'kickoff':kickoff.isoformat()}
                    label = wanted[pair]
                    if label in found:
                        # Two games for one pair/date set are ambiguous.
                        found[label] = None
                    else:
                        found[label] = record
                    break
                except (KeyError, TypeError, ValueError):
                    continue
    return {k:v for k,v in found.items() if v is not None}


def download_lines(games, dates, fetch=None, now=None):
    now = now or datetime.now(timezone.utc)
    if fetch is None:
        def fetch(day):
            url = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=' + day.replace('-','') + '&limit=100'
            with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0 Simmah'}), timeout=12) as response:
                return json.load(response)
    events = []
    for day in sorted(set(dates)):
        events.extend(fetch(day).get('events', []))
    return parse_scoreboard({'events':events}, games, set(dates), now)
