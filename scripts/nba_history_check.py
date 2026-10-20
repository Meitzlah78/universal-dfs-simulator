"""Offline NBA corpus audit. Outputs metadata only; never enables live builds."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
from dataclasses import asdict
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_history import completed_games,download_game
from simmah_nba_possessions import reconstruct
from simmah_nba_rotations import reconstruct_rotations
from simmah_nba_fit import fit_baseline


def run(start,end,before,cache,limit=40,holdout=8):
    if holdout < 1 or limit <= holdout:raise ValueError("Require a positive holdout smaller than the game limit")
    if date.fromisoformat(start)>date.fromisoformat(end):raise ValueError("Start must not follow end")
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    days=[];day=date.fromisoformat(start)
    while day<=date.fromisoformat(end):days.append(day.isoformat());day+=timedelta(days=1)
    schedules=list(ThreadPoolExecutor(3).map(lambda d:completed_games(d,before),days))
    ids=list(dict.fromkeys(i for group in schedules for i in group))[:limit]
    def load(eid):
        p=cache/(eid+'.json')
        if p.exists():
            g=json.loads(p.read_text())
            if date.fromisoformat(g['date'])>=date.fromisoformat(before):raise ValueError('Cached game violates date cutoff')
            return g
        g=download_game(eid,before);p.write_text(json.dumps(g));return g
    def checked_load(eid):
        try:return load(eid),None
        except (ValueError, OSError, KeyError) as exc:
            return None,{'event_id':eid,'reason':str(exc)}
    loaded=list(ThreadPoolExecutor(3).map(checked_load,ids))
    games=[g for g,error in loaded if g is not None]
    rejected=[error for g,error in loaded if error is not None]
    games.sort(key=lambda g:(g['date'],g['event_id']))
    # Hold out complete dates, not just a few games from the final training date.
    if len(games)<=holdout:raise ValueError('Too few games for train/holdout split')
    boundary=games[-holdout]['date']
    training=[g for g in games if g['date']<boundary]
    testing=[g for g in games if g['date']>=boundary]
    model=fit_baseline(training,boundary)
    audits=[]
    for g in games:
        poss=reconstruct(g);rotation=reconstruct_rotations(g)
        audits.append({'event_id':g['event_id'],'date':g['date'],
            'split':'training' if g['date']<boundary else 'holdout',
            'events':len(g['events']),'possession_segments':len(poss),
            'flagged_segments':sum(not r['usable'] for r in poss),
            'points_match':sum(r['points'] for r in poss)==g['home_score']+g['away_score'],
            'rotation_complete':rotation['complete'],'rotation_issues':rotation['issues']})
    return {'requested_games':len(ids),'rejected_games':rejected,'training_games':len(training),'holdout_games':len(testing),
        'holdout_start':boundary,'target_before':before,'rates':asdict(model['rates']),
        'limitations':model['limitations'],'audits':audits,
        'status':'data and reconstruction audit; not a predictive accuracy backtest'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--start',required=True);p.add_argument('--end',required=True)
    p.add_argument('--before',required=True);p.add_argument('--cache',required=True);p.add_argument('--output',required=True)
    p.add_argument('--limit',type=int,default=40);p.add_argument('--holdout',type=int,default=8)
    a=p.parse_args();r=run(a.start,a.end,a.before,a.cache,a.limit,a.holdout)
    Path(a.output).write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='audits'},indent=2))
    print('score ledgers matched',sum(x['points_match'] for x in r['audits']),'/',len(r['audits']))
    print('complete rotations',sum(x['rotation_complete'] for x in r['audits']),'/',len(r['audits']))
