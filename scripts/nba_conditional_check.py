"""Offline event-engine diagnostic conditional on observed player minutes."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_fit import fit_baseline
from simmah_nba_roles import fit_roles
from simmah_nba_rotation_schedule import build_rotation
from simmah_nba_engine import simulate_game
from simmah_nba_markets import simulate_market_game


def check(training,holdout,boundary,before,n=1000,seed=83,markets=None):
    if not isinstance(n,int) or n<1:raise ValueError("Positive integer simulation count required")
    training=list(training);holdout=list(holdout)
    all_ids=[g['event_id'] for g in training+holdout]
    if len(set(all_ids))!=len(all_ids):raise ValueError('Duplicate or overlapping games')
    fitted=fit_baseline(training,boundary)
    roles=fit_roles(training,boundary)
    rows=[]
    for index,g in enumerate(holdout):
        if not boundary<=g['date']<before:raise ValueError('Holdout outside date window')
        if max(int(e['period']['number']) for e in g['events'])!=4:
            rows.append({'event_id':g['event_id'],'excluded':'overtime game'});continue
        teams=[];targets=[];raw_budgets=[]
        for team in g['boxscore']['players']:
            players=[];actual=0
            for section in team['statistics']:
                for athlete in section['athletes']:
                    if athlete.get('didNotPlay') or not athlete.get('stats'):continue
                    stats=dict(zip(section['names'],athlete['stats']))
                    raw=str(stats['MIN'])
                    if raw in ('--',''):continue
                    clock=raw.split(':');minutes=float(clock[0])+(float(clock[1])/60 if len(clock)==2 else 0)
                    if minutes<=0:continue
                    players.append((str(athlete['athlete']['id']),minutes))
                    actual+=float(stats['PTS'])
            budget=sum(m for _,m in players)
            if not 235<=budget<=245:raise ValueError('Incomplete regulation minute ledger')
            teams.append(players);targets.append(actual);raw_budgets.append(budget)
        if len(teams)!=2:raise ValueError('Two team rotations required')
        size=max(map(len,teams));rotations=[];profiles=np.zeros((2,size,5))
        for t,players in enumerate(teams):
            minutes=np.zeros(size)
            for j,(pid,m) in enumerate(players):
                minutes[j]=m*240/raw_budgets[t]
                profiles[t,j]=roles['players'].get(pid,{'rates':roles['pooled_rates']})['rates']
            rotations.append(build_rotation(np.tile(minutes,(n,1)),seed+index*2+t,t*size))
        if markets is None:
            result=simulate_game(np.stack(rotations,axis=1),profiles,[fitted['rates']]*2,seed+index)
        else:
            market=markets[g['event_id']]
            if market['event_id']!=g['event_id'] or market['date']!=g['date']:
                raise ValueError('Historical market identity mismatch')
            target=[market['team_implied_points'][str(t['team']['id'])] for t in g['boxscore']['players']]
            result=simulate_market_game(np.stack(rotations,axis=1),profiles,[fitted['rates']]*2,target,seed+index)
        rows.append({'event_id':g['event_id'],'actual_team_points':targets,
                     'sim_mean_team_points':result['team_points'].mean(axis=0).tolist(),
                     'sim_team_points_sd':result['team_points'].std(axis=0).tolist(),
                     'raw_box_minute_budgets':raw_budgets,
                     'market_calibration':result.get('market_calibration'),
                     'unresolved_tie_fraction':float(result['requires_overtime'].mean())})
    return {'games':rows,'simulations_per_game':n,'boundary':boundary,
            'status':'conditional on actual participating players and minutes; not a pregame backtest',
            'limitations':['actual minutes determine rotation budgets','pooled team shooting efficiencies',
                            'no external player projection anchoring',
                            'no market anchoring' if markets is None else 'archived closing labels not independently frozen pregame','no overtime resolved in this diagnostic']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True);p.add_argument('--audit',required=True)
    p.add_argument('--output',required=True);p.add_argument('--simulations',type=int,default=1000);p.add_argument('--markets')
    a=p.parse_args();audit=json.loads(Path(a.audit).read_text());ids={x['event_id'] for x in audit['audits']}
    games=[json.loads(f.read_text()) for f in Path(a.cache).glob('*.json')]
    games=[g for g in games if g['event_id'] in ids];boundary=audit['holdout_start']
    r=check([g for g in games if g['date']<boundary],[g for g in games if g['date']>=boundary],
            boundary,audit['target_before'],a.simulations,markets=({r['event_id']:r for r in json.loads(Path(a.markets).read_text())} if a.markets else None))
    Path(a.output).write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
