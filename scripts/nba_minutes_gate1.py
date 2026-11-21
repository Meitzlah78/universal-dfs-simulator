"""Frozen offline NBA minutes Gate 1, November 22 through December 1, 2026.

Run with Python, numpy and pandas against validated regular-season
DATE/GAME.json.gz archives. Includes observed-roster matched scoring.
Training ended November 10. Subsequent observations update features only.
No live injury or provider information is used.
"""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date
import argparse
import gzip
import hashlib
import json

import numpy as np
import pandas as pd

START = "2026-11-22"
END = "2026-12-01"
CUTOFF = 0.75
FEATURES = ['last_minutes', 'ewm_minutes', 'trend', 'prior_start_share', 'days_since_observed_game', 'prior_minute_sd', 'prior_dnp_share']
WEIGHTS = {'v1': {'features': ['last_minutes', 'ewm_minutes', 'trend', 'prior_start_share', 'days_since_observed_game', 'prior_minute_sd', 'prior_dnp_share'], 'mean': [18.992449981124953, 18.73880632046198, 0.39333710834277086, 0.38239587265634833, 2.148357870894677, 4.2788156292438755, 0.13596954825720395], 'scale': [12.129785275370068, 11.182058436335467, 5.368059601544006, 0.4556475374681802, 0.8506199539480062, 2.737330767882398, 0.23162987223950185], 'coef': [-2.491684570197336, 0.5228241848647139, 2.2596650340561473, 0.6222736726967648, -0.21750409236565965, 0.3020954822685404, -0.09499080482278395], 'intercept': 0.45298225745564347}, 'participation': {'features': ['days_since_play', 'consecutive_explicit_dnps', 'appearance_rate_10'], 'mean': [2.5436013590033975, 0.18724046810117026, 0.8553784896367002], 'scale': [1.5484150913818269, 0.5587860729809085, 0.23726350831825951], 'coef': [0.1137224092801651, -0.13496704857461805, 1.0679802948764392], 'intercept': 2.387256568784071}}
DEVELOPMENT_ARCHIVE_SHA256 = 'b23fe0f2927429e6231f7c4913c5ee62614eeef6600fdf77d375d61fc7125fd1'


def load_history(root):
    rows=[];issues=[];games=0
    for path in sorted(Path(root).glob('*/*.gz')):
     with gzip.open(path, "rt") as stream:
      g=json.load(stream)
     if g["date"] != path.parent.name or not "2026-10-20" <= g["date"] <= END:
      raise ValueError(f"Unexpected archive date in {path}")
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


def participation_features(actuals):
    history = defaultdict(list)
    rows = []
    for day, group in actuals.groupby("day", sort=True):
        records = group.to_dict("records")
        for row in records:
            prior = history[row["team"], row["pid"]]
            played = [game for game in prior if not game["dnp"] and game["actual_minutes"] > 0]
            recent = prior[-10:]
            if not played:
                continue
            streak = 0
            for game in reversed(prior):
                if not game["dnp"]:
                    break
                streak += 1
            last_played = played[-5:]
            minutes = np.array([game["actual_minutes"] for game in last_played])
            rows.append({
                "game": row["game"], "team": row["team"], "pid": row["pid"],
                "days_since_play": (date.fromisoformat(day) - date.fromisoformat(played[-1]["day"])).days,
                "consecutive_explicit_dnps": streak,
                "appearance_rate_10": sum(not game["dnp"] and game["actual_minutes"] > 0 for game in recent) / len(recent),
                "history_count": len(prior),
                "played_mean_5": float(minutes.mean()),
                "played_ewm_5": float(np.average(minutes, weights=0.7 ** np.arange(len(minutes)-1, -1, -1))),
                "played_last": float(minutes[-1]),
                "played_sd_5": float(minutes.std()),
                "played_starter_share_5": np.mean([bool(game["starter"]) for game in last_played]),
            })
        for row in records:
            history[row["team"], row["pid"]].append(row)
    return pd.DataFrame(rows)


def metrics(actual,pred):
    e=np.asarray(pred)-np.asarray(actual)
    return dict(n=len(e),mae=float(np.abs(e).mean()),rmse=float(np.sqrt((e*e).mean())),bias_prediction_minus_actual=float(e.mean()))


def linear(frame, model):
    inputs = frame[model['features']].to_numpy(float)
    return model['intercept'] + ((inputs - model['mean']) / model['scale']) @ model['coef']


def score(history, *, development_check=False):
    actual, coverage = load_history(history)
    if development_check:
        if coverage['source_sha256'] != DEVELOPMENT_ARCHIVE_SHA256:
            raise ValueError('Development inputs differ from the freeze archive')
        start, end = '2026-11-11', '2026-11-19'
    else:
        start, end = START, END
        if actual.day.max() != END:
            raise ValueError('Archive does not reach the end of the Gate 1 window')
    frame, skips = features(actual)
    frame = frame.merge(participation_features(actual), on=['game', 'team', 'pid'],
                        validate='one_to_one')
    test = frame[frame.day.between(start, end)].copy()
    if test.empty:
        raise ValueError('No matched games in scoring window')
    test['rolling'] = test.baseline
    test['v1'] = np.clip(test.baseline + linear(test, WEIGHTS['v1']), 0, 48)
    probability = 1 / (1 + np.exp(-linear(test, WEIGHTS['participation'])))
    test['v2'] = test.v1 * np.where(test.appearance_rate_10 < CUTOFF, probability, 1.)
    slices = {'overall': test, 'explicit_dnp': test[test.dnp], 'non_dnp': test[~test.dnp]}
    results = {name: {part: metrics(rows.actual_minutes, rows[name]) if len(rows) else None
                      for part, rows in slices.items()}
               for name in ('rolling', 'v1', 'v2')}
    if development_check:
        expected = [5.4578, 8.0304, 5.0863]
        assert len(test) == 1569 and np.allclose([v['mae'] for v in results['v2'].values()], expected, atol=.00006)
    return {'window': [start, end], 'matched_games_by_date': test.groupby('day').game.nunique().to_dict(),
            'actual_games_by_date': actual[actual.day.between(start, end)].groupby('day').game.nunique().to_dict(),
            'source': coverage, 'warmup_skips': skips, 'metrics': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('history', type=Path)
    parser.add_argument('--development-check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(score(args.history, development_check=args.development_check), indent=2, allow_nan=False))
