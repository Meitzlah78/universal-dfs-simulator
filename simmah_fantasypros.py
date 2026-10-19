"""Secret-safe access checks for the official FantasyPros weekly API.

Do not use generic points/points_ppr/points_half as verified DFS projections.
"""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def check_weekly_access(api_key, season, week, opener=urlopen):
    """One small QB request; return only safe metadata, never credentials or body."""
    if not str(api_key or '').strip():
        return {'ok': False, 'status': 'API key is missing from Streamlit Secrets.'}
    season, week = int(season), int(week)
    if not 2020 <= season <= 2100 or not 1 <= week <= 22:
        raise ValueError('Select an explicit NFL season and week (1–22).')
    url = f'https://api.fantasypros.com/public/v2/json/nfl/{season}/projections?' + urlencode({'position':'QB','week':week})
    request = Request(url, headers={'x-api-key':str(api_key).strip(), 'Accept':'application/json'})
    try:
        with opener(request, timeout=12) as response:
            payload = json.load(response)
    except HTTPError as error:
        messages = {401:'Key rejected',403:'Access denied; check projection permissions for your API plan',
                    429:'API request limit reached'}
        return {'ok':False,'status':messages.get(error.code, 'API request failed') + f' (HTTP {error.code}).'}
    except (URLError, TimeoutError, OSError, ValueError):
        return {'ok':False,'status':'API connection timed out or returned an unreadable response.'}
    if not isinstance(payload, dict):
        return {'ok':False,'status':'Unexpected API response format.'}
    if str(payload.get('season')) != str(season) or str(payload.get('week')) != str(week):
        return {'ok':False,'status':'API returned a different season/week; response rejected.'}
    players = payload.get('players')
    if not isinstance(players, list) or not players:
        return {'ok':False,'status':'Connected, but no QB projections were returned for this week.'}
    fields = set()
    for player in players:
        if not isinstance(player, dict):
            continue
        stats = player.get('stats', [])
        if isinstance(stats, dict):
            fields.update(stats)
        elif isinstance(stats, list):
            for entry in stats:
                if isinstance(entry, dict):
                    fields.update(entry)
    # Field names are restricted to documented scoring fields, not arbitrary response text.
    known = {'points','points_half','points_ppr','pass_yds','pass_tds','pass_ints',
             'pass_yds_300','rush_yds','rush_tds','rush_yds_100','fumbles','2pt_tds'}
    return {'ok':True,'status':'Weekly projections access confirmed.', 'season':season,'week':week,
            'qb_players':len(players),'scoring_fields':sorted(fields & known)}
