"""Retrospective top-tier selection sweep; actuals enter evaluation only.

The trace supports the neutral saved manual settings in Monday's FD package.
No winning-roster identity enters deterministic or random selection.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from compare_portfolio_rankings import joint_prizes
from audit_builder_selector import name_key, canonical, score_candidates
from simmah_portfolio_selection import select_portfolio
from simmah_contest_history import read_standings


def incidence(frame,slots):
    values=frame[slots].astype(str).to_numpy();names=np.unique(values);lookup={n:i for i,n in enumerate(names)}
    matrix=np.zeros((len(frame),len(names)),np.int8)
    for i,row in enumerate(values):matrix[i,[lookup[n] for n in row]]=1
    return matrix


def farthest_first(frame,slots,count,maximum):
    """Combination distance only, seeded by best pregame Top1; hard cap fixed."""
    matrix=incidence(frame,slots);used=np.zeros(len(frame),bool);counts=np.zeros(matrix.shape[1],int)
    overlap=np.zeros(len(frame));chosen=[]
    for step in range(count):
        valid=(~used)&np.all(counts+matrix<=maximum,axis=1)
        options=np.flatnonzero(valid)
        if not len(options):raise ValueError('Distance selection cannot fill portfolio under fixed cap')
        # Stable pregame order breaks distance ties; realized points never enter.
        best=int(options[np.argmin(overlap[options])]);chosen.append(best);used[best]=True;counts+=matrix[best]
        overlap=np.maximum(overlap,(matrix@matrix[best])/len(slots))
    return np.array(chosen)


def random_portfolios(frame,slots,count,maximum,trials=1000,seed=20261103):
    """Uniform fixed-size samples conditional on passing the fixed hard cap."""
    rng=np.random.default_rng(seed);matrix=incidence(frame,slots);accepted=[];attempts=0
    while len(accepted)<trials and attempts<trials*100:
        pick=rng.choice(len(frame),count,replace=False);attempts+=1
        if np.all(matrix[pick].sum(axis=0)<=maximum):accepted.append(pick)
    if len(accepted)<trials:raise ValueError('Insufficient valid random portfolios; no cap relaxed')
    return accepted,attempts


def neutral_selector_trace(frame,slots,count=20,diversity=50):
    """Reproduce the neutral-control greedy objective and verify against selector."""
    ranked=frame.sort_values('Top1',ascending=False,kind='stable').reset_index(drop=True)
    matrix=incidence(ranked,slots);counts=np.zeros(matrix.shape[1],int);used=np.zeros(len(ranked),bool);overlap=np.zeros(len(ranked))
    quality=ranked.Top1.to_numpy(float);utility=(quality-quality.min())/max(quality.max()-quality.min(),1e-9)
    strength=diversity/100;maximum=max(1,int(np.floor(count*(100-40*strength)/100+1e-9)))
    steps=[];chosen=[]
    for step in range(count):
        valid=(~used)&np.all(counts+matrix<=maximum,axis=1)
        concentration=(2*(matrix@counts)+len(slots))/count
        objective=utility-strength*concentration-.7*strength*overlap;objective[~valid]=-np.inf
        best=int(objective.argmax())
        if not np.isfinite(objective[best]):raise ValueError('Trace requires repair; not supported by neutral greedy trace')
        steps.append((valid.copy(),objective.copy(),best))
        chosen.append(best);used[best]=True;counts+=matrix[best];overlap=np.maximum(overlap,(matrix@matrix[best])/len(slots))
    check=select_portfolio(frame,slots,count,'Top1',diversity=diversity)
    if {canonical(row,True) for row in check[slots].itertuples(index=False,name=None)}!={canonical(row,True) for row in ranked.iloc[chosen][slots].itertuples(index=False,name=None)}:
        raise ValueError('Trace does not reproduce selector output')
    return ranked,steps


def sweep(build_path,standings_path,trials=1000):
    if not 1<=trials<=100000:raise ValueError('Trials must be between 1 and 100000')
    raw=Path(build_path).read_bytes();outer=zipfile.ZipFile(io.BytesIO(raw))
    manifest=json.loads(outer.read('manifest.json'))
    for filename,entry in manifest['files'].items():
        if hashlib.sha256(outer.read(filename)).hexdigest()!=entry['sha256']:raise ValueError('Build hash mismatch')
    original=zipfile.ZipFile(io.BytesIO(outer.read('original_build.zip')))
    frame=pd.read_csv(io.BytesIO(original.read('scored_lineups.csv')))
    slots=['MVP']+['FLEX'+str(i) for i in range(1,6)]
    if not set(slots+['Top1'])<=set(frame):raise ValueError('This sweep requires FD Single Game columns')
    contest=json.loads(original.read('inputs/contest.json'))
    # Resolve exact entry count and verify neutral manual controls from saved snapshot.
    import base64,gzip,csv
    latest=zipfile.ZipFile(io.BytesIO(outer.read('latest_export_checkpoint.zip')))
    state=json.loads(gzip.decompress(base64.b64decode(latest.read('workspace_snapshot.txt'))))['values']
    encoded=state['fd_player_controls_Single Game'];controls=pd.DataFrame(json.loads(encoded['value'])['data'])
    for column in ['Max Exposure %','MVP Max %','Flex Max %']:
        if column in controls and not pd.to_numeric(controls[column]).eq(100).all():raise ValueError('Trace requires neutral manual maximums')
    for column in ['Lock','Fade']:
        if column in controls and controls[column].astype(bool).any():raise ValueError('Trace requires neutral locks/fades')
    if 'Min Exposure %' in controls and not pd.to_numeric(controls['Min Exposure %']).eq(0).all():raise ValueError('Trace requires zero manual minimums')
    rows=list(csv.reader(io.StringIO(latest.read('export.csv').decode('utf-8-sig'))))
    own_ids=[row[0] for row in rows[1:] if len(row)>1 and row[0].isdigit() and row[1]==str(contest['id'])]
    count=len(own_ids)
    if count!=20 or len(set(own_ids))!=count:raise ValueError('This frozen experiment requires 20 unique original entries')
    ranked,steps=neutral_selector_trace(frame,slots,count,50);top=ranked.head(250).copy();maximum=16
    fixed={name:{'Max Exposure %':80} for name in np.unique(top[slots].astype(str).to_numpy())}
    selected={};effective={}
    for diversity in [0,25,50,75,100]:
        try:
            result=select_portfolio(top,slots,count,'Top1',controls=fixed,diversity=diversity)
            selected['diversity_'+str(diversity)]=result
            effective['diversity_'+str(diversity)]=result.attrs.get('effective_auto_cap_pct')
        except ValueError as error:selected['diversity_'+str(diversity)]=str(error)
    distance=farthest_first(top,slots,count,maximum)
    selected['combination_distance']=top.iloc[distance]
    randoms,attempts=random_portfolios(top,slots,count,maximum,trials)
    # Only now load completed outcomes and identify the hindsight best exemplar.
    standings_raw=Path(standings_path).read_bytes();actual_frame=read_standings(standings_raw,Path(standings_path).name)[0]
    entries=actual_frame.dropna(subset=['Rank','EntryId','Points']).copy();entries['_id']=entries.EntryId.astype('int64').astype(str)
    if entries._id.duplicated().any():raise ValueError('Duplicate standings entry IDs')
    if not set(own_ids)<=set(entries._id):raise ValueError('Original entries not found')
    opponents=entries.loc[~entries._id.isin(own_ids),'Points'].to_numpy(float)
    actual={}
    for name,value in actual_frame[['Player','FPTS']].dropna().itertuples(index=False,name=None):
        key=name_key(name);value=float(value)
        if not np.isfinite(value) or (key in actual and abs(actual[key]-value)>.001):raise ValueError('Invalid/conflicting actual score')
        actual[key]=value
    points,supported=score_candidates(ranked,slots,actual,True)
    if not supported.all():raise ValueError('Full explicit player-score coverage required for this sweep')
    target=int(np.argmax(points));target_key=canonical(ranked.iloc[target][slots],True)
    summaries={}
    def evaluate(portfolio):
        scored,covered=score_candidates(portfolio,slots,actual,True)
        if not covered.all():raise ValueError('Missing actual score')
        ranks,prizes=joint_prizes(scored,opponents,contest['payouts'])
        keys=[canonical(row,True) for row in portfolio[slots].itertuples(index=False,name=None)]
        return {'contains_hindsight_exemplar':target_key in keys,'estimated_net':float(prizes.sum()-count*float(contest['entry_fee'])),
                'best_rank':int(ranks.min()),'maximum_player_entries':int(incidence(portfolio,slots).sum(axis=0).max())}
    for method,portfolio in selected.items():
        summaries[method]={'error':portfolio} if isinstance(portfolio,str) else dict(evaluate(portfolio),preferred_cap_after_any_soft_relaxation=effective.get(method))
    random_results=[evaluate(top.iloc[index]) for index in randoms]
    nets=np.array([r['estimated_net'] for r in random_results]);included=sum(r['contains_hindsight_exemplar'] for r in random_results)
    trace=[{'step':i+1,'target_eligible':bool(valid[target]),'target_objective':float(objective[target]) if np.isfinite(objective[target]) else None,
            'selected_objective':float(objective[best]),'selected_pregame_rank':best+1} for i,(valid,objective,best) in enumerate(steps)]
    return {'schema':1,'contest_id':str(contest['id']),'build_sha256':hashlib.sha256(raw).hexdigest(),'standings_sha256':hashlib.sha256(standings_raw).hexdigest(),
       'outcomes_loaded_after_selection':True,'candidate_filter':'First 250 by pregame Top1, stable ties','hindsight_exemplar_pregame_rank':target+1,
       'hard_overall_cap_entries':16,'manual_role_caps':'100%; no forced exposure targets','neutral_original_selector_trace':trace,
       'target_eligible_every_original_step':all(row['target_eligible'] for row in trace),'deterministic_methods':summaries,
       'random_baseline':{'trials':trials,'attempts':attempts,'seed':20261103,'uniform_unconstrained_specific_lineup_probability':20/250,
          'conditional_hard_cap_exemplar_inclusion_rate':included/trials,'exemplar_included_trials':included,'mean_net':float(nets.mean()),
          'median_net':float(np.median(nets)),'positive_net_trials':int((nets>0).sum())},
       'promotion_accepted':False,'limitations':['Retrospective test of one already inspected game; no negative bias or durable improvement inferred from a single missed winner.',
         'Hard overall cap fixed at 80% for all top-250 experiments; diversity slider also changes its softer preferred cap. Report records any soft relaxation.',
         'Combination distance is a roster-distance heuristic, not coverage of true future game outcomes.',
         'One best-scoring exemplar is tracked; it is not a requirement that any valid portfolio include it.',
         'Actuals never enter selection or random-sample acceptance. No live setting or ranking changed.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);p.add_argument('--standings',required=True);p.add_argument('--output',required=True);p.add_argument('--trials',type=int,default=1000)
    a=p.parse_args();report=sweep(a.build,a.standings,a.trials);Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='neutral_original_selector_trace'},indent=2))

if __name__=='__main__':main()
