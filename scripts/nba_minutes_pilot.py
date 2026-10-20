"""Offline, news-unaware historical minutes baseline. Never changes live models."""
import argparse
from collections import defaultdict
from datetime import date,timedelta
import json
from pathlib import Path
import numpy as np
import pandas as pd
import nba_rotation_coverage as coverage


def evaluate(actuals,boundary='2025-01-08',history_games=5,minimum_games=3):
    if history_games<minimum_games or minimum_games<3:raise ValueError('At least three prior team games required')
    history=defaultdict(list);rows=[];coverage_rows=[]
    for day,day_rows in actuals.groupby('Game Date',sort=True):
        pending=[]
        for (game,team),group in day_rows.groupby(['ESPN Game ID','ESPN Team ID'],sort=True):
            if not np.isfinite(group['Regulation Minutes'].to_numpy(float)).all():raise ValueError('Missing or nonfinite actual minutes')
            if abs(group['Regulation Minutes'].sum()-240)>1e-5:raise ValueError('Unreconciled actual team minutes')
            if group['ESPN Player ID'].duplicated().any():raise ValueError('Duplicate player IDs')
            if (group['Regulation Minutes']<0).any() or (group['Regulation Minutes']>48).any():raise ValueError('Invalid regulation minutes')
            known=history[team][-history_games:]
            current=dict(zip(group['ESPN Player ID'].astype(str),group['Regulation Minutes'].astype(float)))
            if str(day)>=boundary:
                if len(known)<minimum_games:
                    coverage_rows.append({'game':str(game),'team':str(team),'reason':'insufficient prior accepted team games','players':len(group)})
                else:
                    # Each historical vector is a complete 240-minute allocation.
                    # Players absent from a verified complete past team ledger had
                    # no allocated minutes for that team, not missing downloaded stats.
                    ids=sorted({pid for observation in known for pid in observation})
                    samples=np.array([[g.get(pid,0.) for pid in ids] for g in known])
                    assert np.allclose(samples.sum(axis=1),240)
                    for _,player in group.iterrows():
                        pid=str(player['ESPN Player ID'])
                        if pid not in ids:
                            coverage_rows.append({'game':str(game),'team':str(team),'player':pid,'reason':'player absent from prior team history'})
                            continue
                        if player['Actual Status']=='unresolved_zero':
                            coverage_rows.append({'game':str(game),'team':str(team),'player':pid,'reason':'unresolved actual participation status'})
                            continue
                        values=samples[:,ids.index(pid)];actual=float(player['Regulation Minutes']);mean=float(values.mean())
                        low,high=np.quantile(values,[.1,.9]);threshold=30.
                        probability=float((values>=threshold).mean())
                        # Empirical CRPS grades the entire distribution, not only its mean.
                        crps=float(np.abs(values-actual).mean()-.5*np.abs(values[:,None]-values[None,:]).mean())
                        rows.append({'Game Date':str(day),'ESPN Game ID':str(game),'ESPN Team ID':str(team),
                            'ESPN Player ID':pid,'Name':player['Name'],'Actual Minutes':actual,'Mean Minutes':mean,
                            'P10':float(low),'P90':float(high),'Covered 80%':bool(low<=actual<=high),
                            'Absolute Error':abs(mean-actual),'CRPS':crps,'Point Forecast CRPS':abs(mean-actual),
                            'Probability 30+ Minutes':probability,'Brier 30+':(probability-float(actual>=threshold))**2,
                            'Brier 30+ Point Forecast':(float(mean>=threshold)-float(actual>=threshold))**2,
                            'Prior Team Games':len(known),'Verified DNP':player['Actual Status']=='verified_dnp'})
                    for missing in set(ids)-set(current):
                        coverage_rows.append({'game':str(game),'team':str(team),'player':missing,'reason':'forecast player missing from current box roster; not assigned zero'})
            pending.append((team,current))
        # Do not let games on the evaluation date update one another's inputs.
        for team,current in pending:history[team].append(current)
    frame=pd.DataFrame(rows)
    if frame.empty:raise ValueError('No covered holdout player games')
    summary={'boundary':boundary,'history_games':history_games,'minimum_prior_team_games':minimum_games,
        'matched_player_games':len(frame),'evaluated_team_games':len(frame[['ESPN Game ID','ESPN Team ID']].drop_duplicates()),
        'mae':float(frame['Absolute Error'].mean()),'coverage_80':float(frame['Covered 80%'].mean()),
        'mean_interval_width':float((frame.P90-frame.P10).mean()),'empirical_crps':float(frame.CRPS.mean()),
        'point_forecast_crps':float(frame['Point Forecast CRPS'].mean()),'brier_30_plus':float(frame['Brier 30+'].mean()),
        'point_forecast_brier_30_plus':float(frame['Brier 30+ Point Forecast'].mean()),
        'verified_dnp_player_games':int(frame['Verified DNP'].sum()),
        'played_player_mae':float(frame.loc[frame['Actual Minutes']>0,'Absolute Error'].mean()),
        'verified_dnp_mae':float(frame.loc[frame['Verified DNP'],'Absolute Error'].mean()) if frame['Verified DNP'].any() else None,
        'coverage_issues':{str(k):int(v) for k,v in pd.Series([r['reason'] for r in coverage_rows]).value_counts().items()},
        'limitations':['Historical allocation baseline using only previous accepted team games; not the live provider-anchored uncertainty challenger.',
            'No archived pregame injuries, trades, availability, starting-lineup or RotoWire minutes inputs.',
            'Current box roster used only for evaluation matching; coverage failures reported, never filled as DNP.',
            'Small contiguous holdout; no hyperparameters tuned on these results; no predictive edge or ROI claim.']}
    return summary,frame,coverage_rows

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True);p.add_argument('--output-dir',required=True)
    a=p.parse_args();out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    start=date(2025,1,1);coverage.DATES=[(start+timedelta(days=i)).isoformat() for i in range(21)]
    audit=coverage.audit(a.cache)
    audit['limitations'][0]='Contiguous January 1–21, 2025 sample; rejected games excluded and coverage reported.'
    audit['accepted_minutes_export']=coverage.export_minutes(audit,a.cache,out/'accepted-player-minutes.csv')
    (out/'source-audit.json').write_text(json.dumps(audit,indent=2))
    actual=pd.read_csv(out/'accepted-player-minutes.csv',dtype={'ESPN Game ID':str,'ESPN Team ID':str,'ESPN Player ID':str})
    summary,rows,issues=evaluate(actual)
    rows.to_csv(out/'predictions-and-actuals.csv',index=False)
    (out/'coverage-issues.json').write_text(json.dumps(issues,indent=2))
    summary['source_games']=audit['discovered_games'];summary['accepted_games']=audit['accepted_games']
    (out/'results.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2),flush=True)
