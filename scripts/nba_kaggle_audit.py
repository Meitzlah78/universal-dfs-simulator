"""Audit downloaded Eoin Moore Kaggle CSVs; never alters live NBA models."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
import numpy as np


def audit(folder,start='2023-01-01',before='2026-10-20'):
    folder=Path(folder)
    games=pd.read_csv(folder/'Games.csv',dtype={'gameId':str},low_memory=False)
    allowed={'Regular Season','Playoffs','Play-in Tournament','NBA Emirates Cup','Emirates NBA Cup','NBA Cup'}
    dates=pd.to_datetime(games['gameDateTimeEst'],errors='coerce')
    games=games[dates.ge(start)&dates.lt(before)&games.gameType.isin(allowed)].copy()
    ids=set(games.gameId)
    chunks=[]
    for frame in pd.read_csv(folder/'PlayerStatistics.csv',chunksize=100000,
                             dtype={'gameId':str,'personId':str,'playerteamId':str},low_memory=False):
        chunks.append(frame[frame.gameId.isin(ids)].copy())
    players=pd.concat([c for c in chunks if not c.empty],ignore_index=True)
    teams=pd.read_csv(folder/'TeamStatistics.csv',dtype={'gameId':str,'teamId':str},low_memory=False)
    teams=teams[teams.gameId.isin(ids)].copy()
    minutes=pd.to_numeric(players.numMinutes,errors='coerce')
    dnp=players.comment.fillna('').str.match(r'(?i)^(?:DNP|DND|NWT)\b')
    stats=['points','assists','blocks','steals','reboundsTotal','turnovers','fieldGoalsMade','threePointersMade','freeThrowsMade']
    numeric=players[stats].apply(pd.to_numeric,errors='coerce')
    contradiction=dnp & ((minutes>0)|numeric.fillna(0).ne(0).any(axis=1))
    verified_dnp=dnp & ~contradiction
    actual=minutes.copy();actual[verified_dnp]=0
    unresolved=actual.isna()
    # Zero/no-comment rows stay flagged, rather than inventing a DNP reason.
    ledgers=players[['gameId','playerteamId']].copy()
    ledgers['minutes']=actual;ledgers['points']=numeric.points
    ledgers['unresolved']=unresolved;ledgers['contradiction']=contradiction
    grouped=ledgers.groupby(['gameId','playerteamId']).agg(
        minutes=('minutes','sum'),points=('points','sum'),unresolved=('unresolved','sum'),
        contradictions=('contradiction','sum')).reset_index()
    joined=grouped.merge(teams[['gameId','teamId','numMinutes','teamScore']],
        left_on=['gameId','playerteamId'],right_on=['gameId','teamId'],how='outer',validate='one_to_one',indicator=True)
    joined['minutes_reconciled']=joined['_merge'].eq('both') & (abs(joined.minutes-joined.numMinutes)<=1) & joined.unresolved.eq(0) & joined.contradictions.eq(0)
    joined['points_reconciled']=joined['_merge'].eq('both') & joined.points.eq(joined.teamScore)
    joined['regulation_budget']=abs(joined.numMinutes-240)<=.01
    joined['overtime_budget']= (joined.numMinutes>240) & (abs((joined.numMinutes-240)/25-np.round((joined.numMinutes-240)/25))<.001)
    records=[]
    for name in ['Games.csv','PlayerStatistics.csv','TeamStatistics.csv']:
        h=hashlib.sha256()
        with (folder/name).open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        records.append({'file':name,'bytes':(folder/name).stat().st_size,'sha256':h.hexdigest()})
    return {'source':'https://www.kaggle.com/datasets/eoinamoore/historical-nba-data-and-player-box-scores',
        'window':{'start_inclusive':start,'before_exclusive':before},'files':records,
        'games':len(games),'player_rows':len(players),'unique_players':players.personId.nunique(),
        'duplicate_game_player_rows':int(players.duplicated(['gameId','personId']).sum()),
        'latest_game':str(games.gameDateTimeEst.max()),'game_types':games.gameType.value_counts().to_dict(),
        'explicit_nonparticipation_rows':int(verified_dnp.sum()),
        'minute_precision_by_year':{str(year):{'nonmissing':int(g.numMinutes.notna().sum()),'fractional_share':float((g.numMinutes.dropna()%1!=0).mean())} for year,g in players.groupby(players.gameDateTimeEst.str[:4])},'dnp_contradictions':int(contradiction.sum()),
        'unresolved_minutes_rows':int(unresolved.sum()),'zero_minutes_without_nonparticipation_comment':int((minutes.eq(0)&~dnp).sum()),
        'missing_scoring_fields_rows':int(numeric.isna().any(axis=1).sum()),
        'team_games':len(joined),'team_join_counts':joined['_merge'].value_counts().to_dict(),
        'minute_difference_quantiles':(joined.minutes-joined.numMinutes).quantile([0,.25,.5,.75,1]).to_dict(),
        'sample_last_team_games':json.loads(joined.tail(8).drop(columns='_merge').to_json(orient='records')),'minutes_ledgers_reconciled':int(joined.minutes_reconciled.sum()),
        'points_ledgers_reconciled':int(joined.points_reconciled.sum()),
        'regulation_team_games':int(joined.regulation_budget.sum()),
        'overtime_team_games':int(joined.overtime_budget.sum()),
        'other_duration_team_games':int((~joined.regulation_budget & ~joined.overtime_budget).sum()),
        'sample_team_games':json.loads(joined.head(8).drop(columns='_merge').to_json(orient='records')),
        'flagged_team_games':json.loads(joined[~joined.minutes_reconciled|~joined.points_reconciled].head(30).drop(columns='_merge').to_json(orient='records')),
        'limitations':['Internal CSV reconciliation, not independent verification of final games.',
            'No historical pregame projections, news timestamps or DFS ID crosswalk supplied.',
            'Overtime counts inferred only for audit from team-minute budgets, not certified for model training.',
            'No live models changed and no predictive accuracy or ROI result claimed.']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();r=audit(a.folder);Path(a.output).write_text(json.dumps(r,indent=2,allow_nan=False));print(json.dumps({k:v for k,v in r.items() if k not in {'sample_team_games','flagged_team_games'}},indent=2))
