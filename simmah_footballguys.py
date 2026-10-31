"""Public Footballguys main-slate ownership, separate from point projections."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from html import unescape
import re

URL = 'https://www.footballguys.com/dfs-roster-percentages'
ALIASES = {'projected ownership', 'projected own %', 'ownership %', 'ownership', 'projected own', 'own%', 'own'}
DEFENSES = dict(zip(
    ['Arizona Cardinals','Atlanta Falcons','Baltimore Ravens','Buffalo Bills','Carolina Panthers','Chicago Bears','Cincinnati Bengals','Cleveland Browns','Dallas Cowboys','Denver Broncos','Detroit Lions','Green Bay Packers','Houston Texans','Indianapolis Colts','Jacksonville Jaguars','Kansas City Chiefs','Las Vegas Raiders','Los Angeles Chargers','Los Angeles Rams','Miami Dolphins','Minnesota Vikings','New England Patriots','New Orleans Saints','New York Giants','New York Jets','Philadelphia Eagles','Pittsburgh Steelers','San Francisco 49ers','Seattle Seahawks','Tampa Bay Buccaneers','Tennessee Titans','Washington Commanders'],
    ['ARI','ATL','BAL','BUF','CAR','CHI','CIN','CLE','DAL','DEN','DET','GB','HOU','IND','JAX','KC','LV','LAC','LAR','MIA','MIN','NE','NO','NYG','NYJ','PHI','PIT','SF','SEA','TB','TEN','WAS']))


def name_key(value):
    value = unescape(str(value)).lower()
    value = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', value)
    return re.sub('[^a-z0-9]', '', value)


def has_uploaded_ownership(pool):
    import pandas as pd
    import numpy as np
    for column in pool:
        if str(column).strip().lower() in ALIASES:
            values=pd.to_numeric(pool[column].astype(str).str.replace('%','',regex=False),errors='coerce')
            if (np.isfinite(values) & values.between(0,100)).any():return True
    return False


def parse_footballguys(html, site, now=None):
    if site not in {'draftkings', 'fanduel'}:
        raise ValueError('Unsupported ownership site')
    now = now or datetime.now(timezone.utc)
    selected = {}
    for field, body in re.findall(r'<select\b[^>]*name=[\"\'](\w+)[\"\'][^>]*>(.*?)</select>', html, re.I | re.S):
        match = re.search(r'<option\b[^>]*value=[\"\']([^\"\']+)[\"\'][^>]*selected[^>]*>', body, re.I)
        if match:
            selected[field.lower()] = match.group(1)
    if selected.get('site') != site or not selected.get('week', '').isdigit():
        raise ValueError('Ownership site/week metadata missing or mismatched')
    match = re.search(r'Last updated\s*<b>\s*([A-Za-z]{3}, [A-Za-z]{3} \d+ at \d+:\d+ [AP]M GMT)', html)
    if not match:
        raise ValueError('Ownership update time missing')
    updated = datetime.strptime(match.group(1) + ' ' + str(now.year), '%a, %b %d at %I:%M %p GMT %Y').replace(tzinfo=timezone.utc)
    et = ZoneInfo('America/New_York')
    # Limit the public weekly table to a fresh Sunday main slate. No late,
    # afternoon-only, Thursday/Monday or single-game extrapolation.
    if now.astimezone(et).weekday() != 6 or updated.astimezone(et).date() != now.astimezone(et).date() or not -300 <= (now-updated).total_seconds() <= 86400:
        raise ValueError('Ownership is not a fresh Sunday main-slate table')
    values, teams = {}, set()
    for pos, table in re.findall(r'<table\b[^>]*id=[\"\']data-(qb|rb|wr|te|td)[\"\'][^>]*>(.*?)</table>', html, re.I | re.S):
        entries = re.findall(r'<td\b[^>]*class=[\"\']la[\"\'][^>]*>(.*?)</td>\s*<td[^>]*>([\d.]+)%</td>', table, re.I | re.S)
        total = 0
        for raw, raw_value in entries:
            name = unescape(re.sub('<[^>]+>', '', raw)).strip()
            value = float(raw_value)
            if not 0 <= value <= 100:
                raise ValueError('Invalid ownership percentage')
            position = 'DST' if pos.lower() == 'td' else pos.upper()
            if position == 'DST':
                if name not in DEFENSES:
                    raise ValueError('Unknown ownership defense')
                key = (DEFENSES[name], position)
                teams.add(DEFENSES[name])
            else:
                key = (name_key(name), position)
            if key in values:
                raise ValueError('Ambiguous ownership name')
            values[key] = value
            total += value
        bounds = {'qb':(85,110), 'rb':(180,310), 'wr':(280,410), 'te':(85,210), 'td':(85,110)}
        lo, hi = bounds[pos.lower()]
        if not lo <= total <= hi:
            raise ValueError('Ownership totals do not fit a full-roster slate')
    if {p for _,p in values} != {'QB','RB','WR','TE','DST'} or len(teams) < 12:
        raise ValueError('Incomplete main-slate ownership table')
    return values, {'teams':teams, 'week':selected['week'], 'updated':updated.isoformat()}


def apply_footballguys(pool, html, site, now=None):
    import pandas as pd
    result = pool.copy()
    if has_uploaded_ownership(result):
        return result, 'Uploaded ownership retained; automatic ownership skipped.'
    values, meta = parse_footballguys(html, site, now)
    teams = {_team(t) for t in result['Team']}
    if teams != meta['teams']:
        raise ValueError('Footballguys main-slate teams do not match this player pool')
    matches = []
    for row in result.itertuples():
        pos = str(row.Position).upper()
        pos = 'DST' if pos in {'D','DEF','DST'} else pos
        key = _team(row.Team) if pos == 'DST' else name_key(row.Name)
        matches.append(values.get((key,pos)))
    count = sum(v is not None for v in matches)
    if count < 50:
        raise ValueError('Insufficient player matches for main-slate ownership')
    own = pd.Series(matches, index=result.index, dtype=float)
    # Unlisted players are unknown, not a posted zero. Keep their estimated
    # popularity explicit; never advertise the fallback as external ownership.
    from simmah_field_popularity import estimated_field_weights
    proxy = pd.Series(estimated_field_weights(result, pd.to_numeric(result['MeanPoints'],errors='coerce').to_numpy()),index=result.index).clip(lower=1e-8)
    scale = float((own[own.notna()] / proxy[own.notna()]).median())
    result['Projected Ownership'] = own
    result['Ownership Selection Weight'] = own.fillna(proxy * scale).clip(0,100)
    result['Ownership Source'] = ['Footballguys' if v is not None else 'Projection/value fallback (unlisted)' for v in matches]
    result['Ownership Updated UTC'] = meta['updated']
    result['Ownership Week'] = meta['week']
    return result, f"Footballguys {site} ownership: {count}/{len(result)} matched; {len(result)-count} unlisted use estimated popularity. Week {meta['week']}; updated {meta['updated']}. These are projected ownership inputs, not guaranteed final field frequencies."


def _team(value):
    value = str(value).strip().upper()
    return {'LA':'LAR','JAC':'JAX','WSH':'WAS'}.get(value,value)
