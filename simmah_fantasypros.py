"""Secret-safe access checks for the official FantasyPros weekly API.

Do not use generic points/points_ppr/points_half as verified DFS projections.
"""
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def check_weekly_access(api_key, season, week, opener=urlopen, position="QB"):
    """One explicit position request; return only safe metadata, never credentials or body."""
    if not str(api_key or '').strip():
        return {'ok': False, 'status': 'API key is missing from Streamlit Secrets.'}
    season, week = int(season), int(week)
    if not 2020 <= season <= 2100 or not 1 <= week <= 22:
        raise ValueError('Select an explicit NFL season and week (1–22).')
    if position not in {'QB','RB','WR','TE','K','DST'}:
        raise ValueError('Unsupported position')
    url = f'https://api.fantasypros.com/public/v2/json/nfl/{season}/projections?' + urlencode({'position':position,'week':week})
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
        return {'ok':False,'status':f'Connected, but no {position} projections were returned for this week.'}
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
    known.update({'rec_rec','rec_yds','rec_tds','rec_yds_100','ret_tds',
        'fg','fg_att','fg_made','fg_0_19','fg_20_29','fg_30_39','fg_40_49','fg_50',
        'fg_50_plus','xpt','xpt_att','def_sack','def_int','def_td','def_safety',
        'def_fr','def_ff','def_retd','def_pa_a','def_pa_b','def_pa_c',
        'def_pa_d','def_pa_e','def_pa_f','def_pa_g'})
    samples = []
    for player in players:
        if not isinstance(player, dict):
            continue
        stats = player.get('stats', [])
        stats = [stats] if isinstance(stats, dict) else stats
        numeric = []
        for entry in stats if isinstance(stats, list) else []:
            if not isinstance(entry, dict):
                continue
            values = {}
            for field in known & entry.keys():
                try:
                    value = float(entry[field])
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value):
                    values[field] = value
            numeric.append(values)
        # Never export arbitrary metadata or API response/error bodies.
        safe = lambda value: str(value or '').replace(str(api_key), '[redacted]')[:100]
        samples.append({'name':safe(player.get('name')), 'team':safe(player.get('team_id')),
            'position':safe(player.get('position_id')), 'stats':numeric})
    return {'ok':True,'status':'Weekly projections access confirmed.', 'season':season,'week':week,
            'qb_players':len(players) if position == 'QB' else 0,
            'position':position,'player_count':len(players),'scoring_fields':sorted(fields & known),
            'players':samples}


def check_all_positions(api_key, season, week, opener=urlopen):
    """Explicit user-triggered coverage diagnostic; stop on auth/rate errors."""
    reports = []
    for position in ['QB','RB','WR','TE','K','DST']:
        result = check_weekly_access(api_key, season, week, opener, position)
        reports.append(dict(result, position=position))
        if any(code in result['status'] for code in ['HTTP 401','HTTP 403','HTTP 429','missing from']):
            break
    return {'season':int(season),'week':int(week),'positions':reports}
