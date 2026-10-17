"""Resolve NFL game venues/times and select only in-game NWS forecast hours."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math
import re

ET = ZoneInfo('America/New_York')
# Verified ESPN venue IDs. Neutral/overseas/unmapped venues are never replaced
# with the nominal home team's stadium. NWS does not cover overseas games.
VENUES = {
    '3679': (41.5061,-81.6995,False), '3738': (42.0909,-71.2643,False),
    '3839': (40.8135,-74.0745,False), '3806': (39.9008,-75.1675,False),
    '3886': (27.9759,-82.5033,False), '3622': (39.0489,-94.4839,False),
    '3798': (44.5013,-88.0622,False), '7065': (33.9535,-118.3392,True),
}
# Names supplement IDs for outdoor stadiums whose IDs aren't in the active slate.
# These map the actual venue name, never the participating team's home city.
VENUE_NAMES = {
    'highmarkstadium': (42.7738,-78.7870,False),
    'mtbankstadium': (39.2780,-76.6227,False),
    'bankofamericastadium': (35.2258,-80.8528,False),
    'soldierfield': (41.8623,-87.6167,False),
    'paycorstadium': (39.0955,-84.5161,False),
    'empowerfieldatmilehigh': (39.7439,-105.0201,False),
    'hardrockstadium': (25.9580,-80.2389,False),
    'acrisurestadium': (40.4468,-80.0158,False),
    'lumenfield': (47.5952,-122.3316,False),
    'levisstadium': (37.4030,-121.9700,False),
    'nissanstadium': (36.1665,-86.7713,False),
    'northweststadium': (38.9076,-76.8645,False),
}


def team_key(value):
    key = str(value or '').strip().upper()
    return {'JAC':'JAX','WSH':'WAS','OAK':'LV','SD':'LAC','LA':'LAR'}.get(key,key)


def parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (TypeError,ValueError):
        return None


def parse_wind_mph(value):
    if isinstance(value,dict):
        number, unit = value.get('value'), str(value.get('unitCode','')).lower()
        try:
            number = float(number)
        except (TypeError,ValueError):
            return None
        if not math.isfinite(number):
            return None
        if 'km' in unit: number *= .621371
        elif 'm_s' in unit or 'm/s' in unit: number *= 2.23694
        elif 'kt' in unit or 'knot' in unit: number *= 1.15078
        elif 'mi' not in unit and 'mph' not in unit: return None
        return max(0.,number)
    text = str(value or '').lower()
    if 'calm' in text:
        return 0.
    numbers = re.findall(r'\d+(?:\.\d+)?',text)
    return max(map(float,numbers)) if numbers else None


def kickoff_hints(records):
    """DK Game Info dates/times are Eastern. FD dates may be absent."""
    result = {}
    for row in records:
        lookup = {str(k).casefold().replace(' ',''):v for k,v in row.items()}
        raw = str(lookup.get('gameinfo') or lookup.get('game') or '')
        matchup = re.search(r'\b([A-Z]{2,3})\s*@\s*([A-Z]{2,3})\b',raw.upper())
        if not matchup:
            continue
        pair = tuple(sorted(team_key(x) for x in matchup.groups()))
        match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})(?:\s+(\d{1,2}:\d{2}\s*[AP]M))?',raw,re.I)
        if match:
            value = match.group(1) + (' '+match.group(2).replace(' ','') if match.group(2) else '')
            fmt = '%m/%d/%Y %I:%M%p' if match.group(2) else '%m/%d/%Y'
            try:
                result[pair] = datetime.strptime(value,fmt).replace(tzinfo=ET)
            except ValueError:
                pass
    return result


def schedule_games(payload):
    games = []
    for event in payload.get('events',[]):
        for comp in event.get('competitions',[]):
            teams = {x.get('homeAway'):team_key(x.get('team',{}).get('abbreviation')) for x in comp.get('competitors',[])}
            kickoff = parse_time(comp.get('date') or event.get('date'))
            if not teams.get('home') or not teams.get('away') or kickoff is None:
                continue
            games.append(dict(home=teams['home'],away=teams['away'],kickoff=kickoff,
                              venue=comp.get('venue',{}),id=str(event.get('id',''))))
    return games


def select_game(games, team, opponent, now, hint=None):
    pair = {team_key(team),team_key(opponent)}
    matches = [g for g in games if {g['home'],g['away']} == pair]
    if hint is not None:
        matches = [g for g in matches if g['kickoff'].astimezone(ET).date()==hint.astimezone(ET).date()]
    else:
        matches = [g for g in matches if now-timedelta(hours=4) <= g['kickoff'] <= now+timedelta(days=8)]
    # Ambiguous/unverified schedules must not choose an arbitrary game.
    return matches[0] if len(matches)==1 else None


def venue_location(venue):
    key = str(venue.get('id',''))
    if key in VENUES:
        return VENUES[key]
    if venue.get('indoor') is True:
        return None,None,True
    name = re.sub(r'[^a-z0-9]','',str(venue.get('fullName','')).casefold())
    return VENUE_NAMES.get(name)


def forecast_for_game(periods, kickoff):
    end = kickoff+timedelta(hours=4)
    selected = []
    for p in periods:
        start, stop = parse_time(p.get('startTime')),parse_time(p.get('endTime'))
        if start is not None and stop is not None and start < end and stop > kickoff:
            selected.append(p)
    if not selected:
        return dict(status='Unavailable: no forecast for kickoff window')
    intervals = sorted((parse_time(p['startTime']), parse_time(p['endTime'])) for p in selected)
    covered_until = kickoff
    for start, stop in intervals:
        if start > covered_until:
            return dict(status='Unavailable: incomplete kickoff forecast window')
        covered_until = max(covered_until, stop)
    if covered_until < end:
        return dict(status='Unavailable: incomplete kickoff forecast window')
    winds = [parse_wind_mph(p.get('windSpeed')) for p in selected]
    if any(x is None for x in winds):
        return dict(status='Unavailable: wind forecast missing')
    pops = [(p.get('probabilityOfPrecipitation') or {}).get('value') for p in selected]
    precipitation = [float(x) for x in pops if x is not None]
    snow = any(any(term in str(p.get('shortForecast','')).casefold() for term in ('heavy snow','blizzard')) for p in selected)
    return dict(status='Available', wind_mph=sum(winds)/len(winds),
                precip_pct=max(precipitation) if precipitation else None, heavy_snow=snow,
                summary=' / '.join(dict.fromkeys(str(p.get('shortForecast','')) for p in selected)),
                window_start=kickoff.isoformat(),window_end=end.isoformat())


def weather_factors(weather):
    """Conservative model assumptions applied to events, not source projections."""
    if not weather or weather.get('status') != 'Available' or weather.get('indoor'):
        return dict(completion=1.,pass_yards=1.,rush_share=0.,kick_accuracy=1.)
    wind = float(weather.get('wind_mph',0))
    completion, yards, rush, kick = (1.,1.,0.,1.)
    if wind >= 20: completion,yards,rush,kick = .94,.93,.04,.86
    elif wind >= 15: completion,yards,rush,kick = .97,.97,.02,.94
    elif wind >= 10: completion,yards,kick = .995,.99,.98
    if float(weather.get('precip_pct') or 0) >= 60:
        completion *= .99; yards *= .99; kick *= .98
    if weather.get('heavy_snow'):
        completion *= .95; yards *= .95; rush += .02; kick *= .92
    return dict(completion=completion,pass_yards=yards,rush_share=rush,kick_accuracy=kick)
