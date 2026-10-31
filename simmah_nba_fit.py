"""Offline pooled NBA event-rate baseline, never a calibrated production model.

Free-throw trips are approximated as FTA/2 because the forward core currently
models two-shot trips. Technicals, and-ones and three-shot fouls need explicit
future models. Team turnovers and personal turnovers are also not separated in
the forward core. These limitations prohibit enabling builds from this fit.
"""
from datetime import date
from collections import Counter
from simmah_nba_engine import EventRates


def fit_baseline(games, before, minimum_games=30):
    games=list(games);cutoff=date.fromisoformat(str(before))
    if minimum_games<1 or len(games)<minimum_games:
        raise ValueError('Insufficient completed historical NBA games')
    ids=[g['event_id'] for g in games]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate historical NBA games')
    counts=Counter();seconds=0
    for game in games:
        if date.fromisoformat(game['date'])>=cutoff:
            raise ValueError('Historical fit would use target-slate or future results')
        teams=game['boxscore']['teams']
        if len(teams)!=2:raise ValueError('Two NBA team box scores required')
        periods=max(int(e['period']['number']) for e in game['events'])
        if periods<4:raise ValueError('Incomplete historical NBA game')
        seconds+=2880+max(0,periods-4)*300
        for row in teams:
            stats={s['name']:s['displayValue'] for s in row['statistics']}
            def pair(key):
                made,attempts=map(float,stats[key].split('-'))
                if not 0<=made<=attempts:raise ValueError('Invalid NBA shooting box score')
                return made,attempts
            fg,fga=pair('fieldGoalsMade-fieldGoalsAttempted')
            th,tha=pair('threePointFieldGoalsMade-threePointFieldGoalsAttempted')
            ft,fta=pair('freeThrowsMade-freeThrowsAttempted')
            if tha>fga or th>fg:raise ValueError('Invalid NBA three-point totals')
            counts.update({'fg':fg,'fga':fga,'three':th,'three_a':tha,'ft':ft,'fta':fta})
            for target,source in [('ast','assists'),('stl','steals'),('blk','blocks'),('to','totalTurnovers'),('oreb','offensiveRebounds'),('dreb','defensiveRebounds')]:
                value=float(stats[source])
                if value<0:raise ValueError('Negative historical NBA counting stat')
                counts[target]+=value
    trips=counts['fta']/2
    actions=counts['fga']+trips+counts['to']
    def ratio(a,b):
        if b<=0:raise ValueError('Insufficient NBA event observations')
        return min(1.,max(0.,a/b))
    rates=EventRates(ratio(counts['to'],actions),ratio(trips,actions),
        ratio(counts['three_a'],counts['fga']),
        ratio(counts['fg']-counts['three'],counts['fga']-counts['three_a']),
        ratio(counts['three'],counts['three_a']),ratio(counts['ft'],counts['fta']),
        ratio(counts['ast'],counts['fg']),ratio(counts['oreb'],counts['oreb']+counts['dreb']),
        ratio(counts['stl'],counts['to']),ratio(counts['blk'],counts['fga']-counts['fg']),seconds/actions)
    rates.validate()
    return {'rates':rates,'games':len(games),'event_ids':ids,'before':cutoff.isoformat(),
        'latest_game':max(g['date'] for g in games),'counts':dict(counts),
        'status':'experimental pooled baseline; not validated for builds',
        'limitations':['FTA/2 approximates free throw trips','team/personal turnovers not separated','no opponent or player-specific efficiencies']}
