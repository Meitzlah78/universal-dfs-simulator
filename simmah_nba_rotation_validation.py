"""Offline reconciliation of reconstructed rotations with final NBA box scores."""
from collections import defaultdict
import math
from simmah_nba_rotations import identity,seconds

def reconcile_boxscore(stints,payload,tolerance_seconds=2.):
    if not math.isfinite(tolerance_seconds) or not 0<=tolerance_seconds<=5:
        raise ValueError('Explicit minute tolerance from zero to five seconds required')
    game=payload['game'];gid=identity(game['gameId'])
    if game.get('gameStatus')!=3:raise ValueError('Final NBA box score required')
    periods=int(game['period'])
    if periods<4:raise ValueError('Incomplete box score periods')
    expected=5*(2880+300*(periods-4))
    actual={};teams=set()
    for label in ['homeTeam','awayTeam']:
        team=game[label];tid=identity(team['teamId']);teams.add(tid)
        total=0
        for player in team['players']:
            pid=identity(player['personId']);key=(tid,pid)
            if pid is None or key in actual:raise ValueError('Missing or duplicate player ID')
            minute=player.get('statistics',{}).get('minutes')
            if minute in (None,''):
                if str(player.get('played','')).casefold() not in {'0','false'}:
                    raise ValueError('Unknown player minutes are not a verified DNP')
                value=0.
            else:value=seconds(minute)
            if value>2880+300*(periods-4):raise ValueError('Impossible player minutes')
            actual[key]=value;total+=value
        if abs(total-expected)>tolerance_seconds*len(team['players']):
            raise ValueError('Box score team minute total is incomplete')
    if len(teams)!=2:raise ValueError('Two distinct teams required')
    reconstructed=defaultdict(float);team_seconds=defaultdict(float)
    for stint in stints:
        if identity(stint['game_id'])!=gid:raise ValueError('PBP and box score game IDs differ')
        tid=identity(stint['team']);players=list(map(identity,stint['players']))
        duration=float(stint['seconds'])
        if tid not in teams or len(players)!=5 or len(set(players))!=5 or None in players or not math.isfinite(duration) or duration<=0:
            raise ValueError('Invalid reconstructed stint')
        team_seconds[tid]+=duration*5
        for pid in players:reconstructed[tid,pid]+=duration
    if set(team_seconds)!=teams or any(abs(v-expected)>.01 for v in team_seconds.values()):
        raise ValueError('Reconstructed team minutes do not cover the final game')
    rows=[]
    for key in sorted(set(actual)|set(reconstructed)):
        known=key in actual
        diff=reconstructed.get(key,0)-actual[key] if known else None
        rows.append({'team':key[0],'player_id':key[1],'reconstructed_seconds':reconstructed.get(key,0),
            'actual_seconds':actual.get(key),'difference_seconds':diff,
            'status':'unmatched box-score player' if not known else ('matched' if abs(diff)<=tolerance_seconds else 'minute mismatch')})
    passed=all(r['status']=='matched' for r in rows)
    return {'game_id':gid,'passed':passed,'players':rows,
        'max_absolute_error_seconds':max((abs(r['difference_seconds']) for r in rows if r['difference_seconds'] is not None),default=None),
        'tolerance_seconds':tolerance_seconds,'live_enabled':False,
        'status':'player minutes reconciled' if passed else 'quarantine: player attribution failed'}
