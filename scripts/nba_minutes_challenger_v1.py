"""Offline retrospective minutes challenger. Never imported by the live app.

Frozen v1: ridge residual correction, alpha=10; no holdout tuning.
Actual starter/DNP labels are evaluation outputs, never current-game features.
Uses archived observed rosters for matching, not a pregame eligibility model.
"""
from pathlib import Path
from collections import defaultdict,Counter
from datetime import date
import gzip,json,argparse,hashlib
import numpy as np
import pandas as pd

def load_history(root):
    rows=[];issues=[];games=0
    for path in sorted(Path(root).glob('*/*.gz')):
     g=json.load(gzip.open(path,'rt'));assert '2026-11-01'<=g['date']<='2026-11-19'
     teams=g['boxscore']['players'];assert len(teams)==2
     game=[]
     for team in teams:
      tables=team['statistics'];table=next((x for x in tables if 'MIN' in x['names']),None)
      if table is None:issues.append((g['event_id'],'missing MIN table'));continue
      for a in table['athletes']:
       vals=dict(zip(table['names'],a['stats']));dnp=a.get('didNotPlay') is True
       if dnp:m=0.;fp=0.
       else:
        try:
         minute=str(vals['MIN']);parts=minute.split(':');m=float(parts[0])+(float(parts[1])/60 if len(parts)==2 else 0)
         v={c:float(vals[c]) for c in ['PTS','REB','AST','STL','BLK','TO']}
         threes=float(vals['3PT'].split('-')[0]);doubles=sum(v[c]>=10 for c in ['PTS','REB','AST','STL','BLK'])
         fp=v['PTS']+1.25*v['REB']+1.5*v['AST']+2*(v['STL']+v['BLK'])-.5*v['TO']+.5*threes+1.5*(doubles>=2)+3*(doubles>=3)
        except (ValueError,KeyError,IndexError):issues.append((g['event_id'],a['athlete']['id'],'missing/invalid stats'));continue
       game.append(dict(day=g['date'],game=g['event_id'],team=team['team']['id'],pid=a['athlete']['id'],name=a['athlete']['displayName'],actual_minutes=m,actual_fp=fp,starter=a.get('starter'),dnp=dnp))
     if len({(x['team'],x['pid']) for x in game})!=len(game):raise ValueError('duplicate player game')
     rows.extend(game);games+=1
    manifest=[(str(p.relative_to(root)),hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(Path(root).glob('*/*.gz'))]
    return pd.DataFrame(rows),dict(archived_games=games,player_games=len(rows),issues=issues,source_sha256=hashlib.sha256(json.dumps(manifest).encode()).hexdigest())

FEATURES=['last_minutes','ewm_minutes','trend','prior_start_share','days_since_observed_game','prior_minute_sd','prior_dnp_share']

def features(actuals):
    history=defaultdict(list);out=[];skips=Counter()
    for day,group in actuals.groupby('day',sort=True):
        pending=[]
        for r in group.to_dict('records'):
            h=history[r['team'],r['pid']]
            if len(h)<3:skips['fewer than three prior observed player-team games']+=1
            elif sum(x['actual_minutes'] for x in h[-5:])<=0:skips['no positive historical minutes']+=1
            else:
                known=h[-5:];v=np.array([x['actual_minutes'] for x in known]);w=.7**np.arange(len(v)-1,-1,-1)
                assert h[-1]['day']<day
                out.append({**r,'baseline':float(v.mean()),'last_minutes':float(v[-1]),'ewm_minutes':float(np.average(v,weights=w)),
                    'trend':float(v[-1]-v.mean()),'prior_start_share':float(np.mean([bool(x['starter']) for x in known])),
                    'days_since_observed_game':min(14,(date.fromisoformat(day)-date.fromisoformat(h[-1]['day'])).days),
                    'prior_minute_sd':float(v.std()),'prior_dnp_share':float(np.mean([x['dnp'] for x in known])),
                    'newest_history':h[-1]['day']})
            pending.append(r)
        for r in pending:history[r['team'],r['pid']].append(r)
    return pd.DataFrame(out),dict(skips)

def metrics(actual,pred):
    e=np.asarray(pred)-np.asarray(actual)
    return dict(n=len(e),mae=float(np.abs(e).mean()),rmse=float(np.sqrt((e*e).mean())),bias_prediction_minus_actual=float(e.mean()))

def evaluate(frame,split='2026-11-14'):
    train=frame[frame.day<split];test=frame[frame.day>=split].copy()
    if train.empty or test.empty:raise ValueError('Nonempty chronological training and holdout required')
    x=train[FEATURES].to_numpy(float);mean=x.mean(axis=0);scale=x.std(axis=0);scale[scale==0]=1
    x=np.column_stack([np.ones(len(x)),(x-mean)/scale]);target=(train.actual_minutes-train.baseline).to_numpy()
    penalty=np.eye(x.shape[1])*10;penalty[0,0]=0
    beta=np.linalg.solve(x.T@x+penalty,x.T@target)
    xt=np.column_stack([np.ones(len(test)),(test[FEATURES].to_numpy(float)-mean)/scale])
    test['challenger']=np.clip(test.baseline.to_numpy()+xt@beta,0,48)
    summary={'provenance':'Retrospective Replay','live_enabled':False,'split':split,
        'training_player_games':len(train),'holdout_games':int(test.game.nunique()),'holdout_dates':sorted(test.day.unique()),
        'baseline':metrics(test.actual_minutes,test.baseline),'challenger':metrics(test.actual_minutes,test.challenger),
        'features':FEATURES,'ridge_alpha':10,'subgroups':{},
        'limitations':['No current-game injury, lineup or betting snapshots. Prior starter flags only.',
            'Days since last observed player game is not verified team rest; archive gaps can inflate it.',
            'Observed box rosters define evaluation matching; not a complete pregame player universe.',
            'Rounded full-game box minutes include overtime. Predictions bounded at 48.',
            'Small one-window holdout; no provider-edge, lineup or ROI claim. No holdout tuning.',
            'Earlier same-sample descriptive analysis means this is not a fully untouched external validation set.']}
    for label,mask in [('actual_starter',test.starter==True),('actual_bench',test.starter==False),('verified_dnp',test.dnp==True)]:
        q=test[mask];summary['subgroups'][label]={'baseline':metrics(q.actual_minutes,q.baseline),'challenger':metrics(q.actual_minutes,q.challenger)}
    return summary,test

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--history',required=True);a=p.parse_args()
    actual,coverage=load_history(a.history);frame,skips=features(actual);summary,results=evaluate(frame)
    summary['source_coverage']=coverage;summary['warmup_skips']=skips
    print(json.dumps(summary,indent=2))
