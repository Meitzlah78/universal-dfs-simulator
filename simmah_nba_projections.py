"""Public DFF NBA projections, restricted to the uploaded slate date and games."""
from datetime import date
from html.parser import HTMLParser
from urllib.request import Request, urlopen
import math
import re
import pandas as pd


def slate_date(filename):
    match = re.search(r'NBA-(\d{4}-\d{2}-\d{2})-', filename)
    if not match:
        raise ValueError('NBA slate date is missing from the original filename')
    return date.fromisoformat(match[1]).isoformat()


class ProjectionTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []

    def handle_starttag(self, tag, attrs):
        row = dict(attrs)
        if tag == 'tr' and 'data-ppg_proj' in row:
            self.rows.append(row)


def positive(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, TypeError):
        return None


def parse_dff(html, day, pool):
    parser = ProjectionTable()
    parser.feed(html)
    games = {(str(r.Team).upper(), str(r.Opponent).upper()) for r in pool.itertuples()}
    values = {}
    for row in parser.rows:
        team, opp = row.get('data-team','').upper(), row.get('data-opp','').upper()
        if row.get('data-start_date') != day or (team, opp) not in games:
            continue
        value = positive(row.get('data-ppg_proj'))
        if value is None:
            continue
        key = (row.get('data-name','').strip().casefold(), team)
        if key in values and values[key] != value:
            raise ValueError('Conflicting NBA projections for the same player')
        values[key] = value
    if not values:
        raise ValueError('No positive DFF projections match the NBA slate date and games')
    return values


def download_dff(day, pool):
    day = date.fromisoformat(day).isoformat()
    url = f'https://www.dailyfantasyfuel.com/nba/projections/fanduel/{day}/'
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=15) as response:
        return parse_dff(response.read().decode('utf-8'), day, pool)


def apply_projections(pool, automatic, uploaded=None):
    result = pool.copy()
    overrides = {}
    if uploaded is not None:
        if not {'Player ID','Projection'} <= set(uploaded.columns):
            raise ValueError('Projection CSV requires Player ID and Projection columns')
        if uploaded['Player ID'].astype(str).duplicated().any():
            raise ValueError('Projection CSV contains duplicate Player IDs')
        known = set(pool['Player ID'].astype(str))
        if not set(uploaded['Player ID'].astype(str)) <= known:
            raise ValueError('Projection CSV contains players from another NBA slate')
        overrides = dict(zip(uploaded['Player ID'].astype(str), uploaded['Projection']))
    projections, sources = [], []
    for row in result.itertuples(index=False, name=None):
        player = dict(zip(result.columns, row))
        pid = str(player['Player ID'])
        if pid in overrides:
            value, source = positive(overrides[pid]), 'Uploaded CSV'
        else:
            value = automatic.get((player['Name'].strip().casefold(), player['Team'].upper()))
            value, source = positive(value), 'DFF'
        projections.append(value)
        sources.append(source if value is not None or pid in overrides else 'Missing')
    result['Projection'] = projections
    result['Projection Source'] = sources
    result['Eligible'] = result['Projection'].notna() & ~result['Injury Status'].isin(['Out','O','OUT'])
    return result
