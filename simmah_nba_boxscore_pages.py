"""Offline official NBA public-page box scores; no live app dependency."""
import copy,json,re
from urllib.request import urlopen

def parse_boxscore_page(html,game_id):
    if not re.fullmatch(r'\d{10}',str(game_id)):raise ValueError('Ten-digit NBA game ID required')
    match=re.search(r'<script\b(?=[^>]*\bid=["\\\']__NEXT_DATA__["\\\'])[^>]*>(.*?)</script>',html,re.S)
    if not match:raise ValueError('Official page has no embedded game data')
    game=copy.deepcopy(json.loads(match[1])['props']['pageProps']['game'])
    if str(game['gameId'])!=str(game_id):raise ValueError('NBA page game ID mismatch')
    if game.get('gameStatus')!=3:raise ValueError('NBA game is not final')
    for label in ['homeTeam','awayTeam']:
        for player in game[label]['players']:
            stats=player.setdefault('statistics',{});minute=stats.get('minutes')
            if minute:
                m=re.fullmatch(r'(\d+):(\d{2}(?:\.\d+)?)',str(minute))
                if m:
                    sec=float(m[2])
                    if sec>60:raise ValueError('Invalid player minutes')
                    # Public pages occasionally round displayed seconds to :60.
                    total=60*int(m[1])+sec
                    stats['minutes']=f'PT{int(total//60)}M{total%60}S'
                elif not str(minute).startswith('PT'):raise ValueError('Invalid player minutes')
            elif str(player.get('comment','')).startswith(('DNP -','DND -','NWT -')):
                player['played']='0'
            # All other missing records remain unknown for reconciliation.
    return {'game':game,'source_url':'https://www.nba.com/game/'+str(game_id)+'/box-score'}

def download_boxscore_page(game_id):
    if not re.fullmatch(r'\d{10}',str(game_id)):raise ValueError('Ten-digit NBA game ID required')
    url='https://www.nba.com/game/'+str(game_id)+'/box-score'
    with urlopen(url,timeout=15) as response:
        data=response.read(5_000_001)
    if len(data)>5_000_000:raise ValueError('NBA page exceeds bounded download')
    return parse_boxscore_page(data.decode('utf-8'),game_id)
