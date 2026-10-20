"""Historical ESPN NBA event loader with final-game and pre-slate date guards.

Events are not yet possession boundaries. Offensive rebounds, free-throw trips,
period endings and substitutions require a separate reconstruction stage.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo
from urllib.request import urlopen
import json

BASE='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/'


def parse_game(payload, event_id, before):
    header=payload.get('header',{})
    if str(header.get('id'))!=str(event_id):
        raise ValueError('NBA event ID mismatch')
    comps=header.get('competitions',[])
    if len(comps)!=1 or not comps[0].get('status',{}).get('type',{}).get('completed'):
        raise ValueError('Only completed NBA games may enter historical training')
    competition=comps[0]
    timestamp=competition.get('date') or header.get('date')
    if not timestamp:
        raise ValueError('NBA game timestamp is missing')
    played=datetime.fromisoformat(timestamp.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date()
    cutoff=date.fromisoformat(str(before))
    if played>=cutoff:
        raise ValueError('Historical game must precede the target slate date')
    teams=competition.get('competitors',[])
    if len(teams)!=2:
        raise ValueError('NBA game must contain exactly two teams')
    final={t['homeAway']:int(t['score']) for t in teams}
    events=payload.get('plays',[])
    if not events or len({str(e['id']) for e in events})!=len(events):
        raise ValueError('NBA play-by-play is missing or contains duplicate event IDs')
    # Validate source completeness using the score ledger, not text inference.
    last=events[-1]
    if int(last['homeScore'])!=final['home'] or int(last['awayScore'])!=final['away']:
        raise ValueError('NBA play-by-play final score does not match the official box score')
    if not payload.get('boxscore',{}).get('players'):
        raise ValueError('NBA player box score is missing')
    return {'event_id':str(event_id),'date':played.isoformat(),'source':'ESPN',
        'home_score':final['home'],'away_score':final['away'],
        'events':events,'boxscore':payload['boxscore']}


def download_game(event_id, before, opener=urlopen):
    event_id=str(event_id)
    if not event_id.isdigit():raise ValueError('Numeric NBA event ID required')
    with opener(BASE+'summary?event='+event_id,timeout=15) as response:
        return parse_game(json.load(response),event_id,before)


def completed_games(day, before, opener=urlopen):
    day=date.fromisoformat(str(day))
    if day>=date.fromisoformat(str(before)):
        raise ValueError('Historical schedule must precede the slate')
    with opener(BASE+'scoreboard?dates='+day.strftime('%Y%m%d')+'&limit=100',timeout=15) as response:
        payload=json.load(response)
    return [str(e['id']) for e in payload.get('events',[])
        if e.get('status',{}).get('type',{}).get('completed')]
