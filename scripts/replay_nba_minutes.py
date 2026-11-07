"""Compare regulation minute laws using a pre-lock DK build and final standings.
Usage: python scripts/replay_nba_minutes.py BUILD.zip STANDINGS.zip [--salary-aware]
Uses the current builder in both arms. Portfolio payouts are marginal estimates
against the original contest, with all ties splitting the relevant prize tiers.
"""
import argparse
import io
import json
import re
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_engine import EventRates
from simmah_nba_ownership import field_ownership_inputs
from simmah_nba_pipeline import run_pipeline
from simmah_nba_pregame import PregameEngine
from simmah_nba_rules import rules_for


def key(name):
    plain=unicodedata.normalize('NFKD',str(name)).encode('ascii','ignore').decode().lower()
    return re.sub('[^a-z0-9]','',plain)


def replay(build_path,standings_path,salary_aware):
    with zipfile.ZipFile(build_path) as outer:
        payload=(outer.read('original_build.zip') if 'original_build.zip' in outer.namelist()
                 else Path(build_path).read_bytes())
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        def load(path):return json.loads(z.read(path))
        p=pd.read_csv(z.open('inputs/player_pool.csv'),dtype={'Player ID':str})
        p.attrs.update(load('inputs/player_pool.json')['attrs'])
        markets=load('inputs/markets.json')
        rates=EventRates(**load('inputs/engine.json')['rates'])
        settings=load('inputs/settings.json')
        excluded_ids=list(map(str,load('solver/diagnostics.json').get('excluded_player_ids',[])))
        with np.load(io.BytesIO(z.read('solver/arrays.npz'))) as arrays:payout=arrays['payouts']
        contest_id=str(load('inputs/contest.json')['id'])
    if rules_for(p)['platform']!='DraftKings' or contest_id not in Path(standings_path).name:
        raise ValueError('Use a DK archive and the corresponding contest-standings-ID file')
    s=pd.read_csv(standings_path)
    actual=s.dropna(subset=['Player','FPTS']).assign(key=lambda f:f.Player.map(key))
    if actual.groupby('key').FPTS.nunique().max()!=1 or p.loc[p.Eligible,'Name'].map(key).duplicated().any():
        raise ValueError('Ambiguous points/name mapping: reconcile player IDs before scoring')
    truth=p.Name.map(key).map(actual.groupby('key').FPTS.first()).to_numpy()
    field_points=s.dropna(subset=['Rank','Points']).Points.to_numpy()
    low=p.Eligible & p['Projected Minutes'].lt(18) & np.isfinite(truth)
    own=field_ownership_inputs(p)
    for mode in ('fixed','variable','wider'):
        p.attrs['nba_variable_minutes']=mode!='fixed'
        p.attrs['nba_wider_minutes']=mode=='wider'
        engine=PregameEngine(p,markets,rates,platform='DraftKings')
        start=time.perf_counter()
        result=run_pipeline(p,engine,own['weights'],own['source'],payout,settings['entry_fee'],
            settings['portfolio_count'],salary_min=settings['salary_min'],diversity=settings['diversity'],
            correlation=settings['correlation'],seed=settings['seed'],simulations=settings['simulations'],
            candidate_target=settings['candidate_target'],field_support_target=settings['field_support_target'],
            excluded_indices=np.flatnonzero(p['Player ID'].isin(excluded_ids)),
            ownership_mode=own['mode'],salary_aware=salary_aware,capture_diagnostics=True)
        elapsed=time.perf_counter()-start
        draws=result['diagnostics']['outcomes'][str(settings['seed']+2017)]
        port=result['portfolio']
        ids=port[list(rules_for(p)['slots'])].to_numpy()
        scores=pd.Series(truth,index=p['Player ID']).reindex(ids.ravel()).to_numpy().reshape(ids.shape).sum(axis=1)
        if not np.isfinite(scores).all():raise ValueError('Missing actual for selected player')
        prizes=[];ranks=[]
        for score in scores:
            ahead=int((field_points>score).sum()); tied=int((field_points==score).sum())
            ranks.append(1+ahead+tied/2)
            prizes.append(float(payout[ahead:ahead+tied+1].sum()/(tied+1)))
        quantiles=np.quantile(draws[:,low],[.9,.99],axis=0)
        fees=len(port)*settings['entry_fee']
        print(json.dumps(dict(variable_regulation_minutes=mode,seconds=round(elapsed,2),
            mean_finish=float(np.mean(ranks)),cash_rate=float(np.mean(np.array(prizes)>0)),
            roi=(sum(prizes)-fees)/fees if fees else None,
            low_player_exposures={str(p.iloc[i]['Name']):{'candidate_pct':float(100*np.mean(np.any(result['candidates']['indices']==i,axis=1))),
                'portfolio_pct':float(100*np.mean(np.any(ids==p.iloc[i]['Player ID'],axis=1)))} for i in np.flatnonzero(low)},
            low_group_actual_p99=float(np.quantile(truth[low],.99)) if low.any() else None,
            p99_loss=float(np.maximum(.99*(truth[low]-quantiles[1]),-.01*(truth[low]-quantiles[1])).mean()) if low.any() else None,
            low_minute_players=int(low.sum()),average_p90_p99=quantiles.mean(axis=1).tolist(),
            exceeded_p90_p99=(truth[low]>quantiles).sum(axis=1).tolist(),
            mean_predicted_top_one_pct=float(port['Top 1%'].mean()),cashed=sum(x>0 for x in prizes),
            entries=len(port),gross=sum(prizes),fees=fees,net=sum(prizes)-fees)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build');parser.add_argument('standings');parser.add_argument('--salary-aware',action='store_true')
    args=parser.parse_args()
    replay(args.build,args.standings,args.salary_aware)
