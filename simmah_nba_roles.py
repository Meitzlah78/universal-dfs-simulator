"""Offline player allocation weights. Actual holdout minutes are diagnostic inputs."""
from collections import defaultdict
from datetime import date
import math
import numpy as np

ROLES = ('shot', 'assist', 'rebound', 'steal', 'block')


def observations(games, before):
    seen = set()
    cutoff = date.fromisoformat(str(before))
    for game in games:
        if game['event_id'] in seen:
            raise ValueError('Duplicate historical NBA game')
        seen.add(game['event_id'])
        if date.fromisoformat(game['date']) >= cutoff:
            raise ValueError('Player role fit would use future results')
        for team in game['boxscore']['players']:
            for group in team['statistics']:
                for row in group['athletes']:
                    if row.get('didNotPlay') or not row.get('stats'):
                        continue
                    stats = dict(zip(group['names'], row['stats']))
                    if str(stats['MIN']).strip() in ('--', ''):
                        continue
                    clock = str(stats['MIN']).split(':')
                    minutes = float(clock[0]) + (float(clock[1])/60 if len(clock)==2 else 0)
                    if not math.isfinite(minutes) or minutes < 0:
                        raise ValueError('Invalid historical player minutes')
                    if minutes == 0:
                        continue
                    values = np.array([float(stats['FG'].split('-')[1]),
                                       *[float(stats[k]) for k in ('AST','REB','STL','BLK')]])
                    if not np.isfinite(values).all() or (values < 0).any():
                        raise ValueError('Invalid player role counts')
                    yield str(row['athlete']['id']), minutes, values


def fit_roles(games, before, prior_minutes=120):
    """Shrink per-minute counts toward pooled rates; IDs survive team changes."""
    if not math.isfinite(prior_minutes) or prior_minutes <= 0:
        raise ValueError('Positive prior minutes required')
    totals = defaultdict(lambda: [0., np.zeros(5)])
    for pid, minutes, values in observations(games, before):
        totals[pid][0] += minutes
        totals[pid][1] += values
    if not totals:
        raise ValueError('No usable NBA player observations')
    minutes = sum(x[0] for x in totals.values())
    pooled = sum((x[1] for x in totals.values()), np.zeros(5))/minutes
    players = {pid: {'minutes': m, 'rates': ((v+prior_minutes*pooled)/(m+prior_minutes)).tolist()}
               for pid, (m,v) in totals.items()}
    return {'before': str(before), 'roles': ROLES, 'pooled_rates': pooled.tolist(),
            'players': players, 'prior_minutes': prior_minutes,
            'status': 'experimental allocation weights; not calibrated player projections'}


def evaluate_roles(model, games, before):
    """Holdout count MAE using observed minutes, not a pregame forecast."""
    games=list(games)
    errors=[]; baseline=[]; known=0
    for game in games:
        if game['date'] < model['before']:
            raise ValueError('Evaluation overlaps training dates')
    for pid, minutes, actual in observations(games, before):
        pooled=np.asarray(model['pooled_rates'])
        player=model['players'].get(pid)
        rates=np.asarray(player['rates']) if player else pooled
        errors.append(abs(minutes*rates-actual))
        baseline.append(abs(minutes*pooled-actual))
        known += player is not None
    if not errors:
        raise ValueError('No held-out player observations')
    return {'observations':len(errors),'known_player_observations':known,
            'player_rate_mae':dict(zip(ROLES,np.mean(errors,axis=0).tolist())),
            'pooled_rate_mae':dict(zip(ROLES,np.mean(baseline,axis=0).tolist())),
            'status':'conditional on actual minutes; not pregame prediction accuracy'}
