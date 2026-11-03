"""Outcome-blind portfolio challengers; retrospective joint-payout evaluation.

No method can read actual scores during selection. This comparison never
activates a method or treats previously inspected games as prospective tests.
"""
import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_builder_selector import FORMATS, name_key, score_candidates
from simmah_contest_history import read_standings
from simmah_portfolio_selection import select_portfolio, SELECTION_VERSION

METHODS=('top1','win_rate','expected_prize','mean_points','balanced_rank')


def select_challengers(candidates,slots,count,controls,diversity):
    """Only pregame rosters/scores/settings enter this function, never actuals."""
    frame=candidates.copy()
    frame['_balanced_rank']=sum(frame[column].rank(pct=True,method='average') for column in ('_top1','_prize','_mean'))/3
    columns=dict(zip(METHODS,('_top1','_win','_prize','_mean','_balanced_rank')))
    results={}
    for method,column in columns.items():
        try:
            selected=select_portfolio(frame,slots,count,column,controls=controls,diversity=diversity)
            results[method]={'portfolio':selected,'effective_automatic_cap':selected.attrs.get('effective_auto_cap_pct')}
        except ValueError as error:results[method]={'error':str(error)}
    return results


def joint_prizes(points,opponents,tiers):
    """All selected entries replace the identified original entries together."""
    own=np.rint(np.asarray(points)*100).astype(np.int64);other=np.sort(np.rint(np.asarray(opponents)*100).astype(np.int64))
    own_sorted=np.sort(own)
    greater=len(other)-np.searchsorted(other,own,side='right')+len(own)-np.searchsorted(own_sorted,own,side='right')
    equal=np.searchsorted(other,own,side='right')-np.searchsorted(other,own,side='left')+np.searchsorted(own_sorted,own,side='right')-np.searchsorted(own_sorted,own,side='left')
    ranks=greater+1
    payout=np.zeros(max(len(other)+len(own)+2,max(b for a,b,p in tiers)+2))
    for a,b,prize in tiers:payout[a:b+1]=prize
    prefix=np.r_[0,np.cumsum(payout)]
    return ranks,(prefix[ranks+equal]-prefix[ranks])/equal


def control_frame(value):
    if not isinstance(value,dict) or value.get('@')!='frame':raise ValueError('Missing explicit saved control frame')
    return pd.DataFrame(json.loads(value['value'])['data']).set_index('Name').to_dict('index')


def compare(build_path,standings_path):
    raw=Path(build_path).read_bytes();outer=zipfile.ZipFile(io.BytesIO(raw));nested='original_build.zip' in outer.namelist()
    if nested:
        outer_manifest=json.loads(outer.read('manifest.json'))
        for filename,entry in outer_manifest['files'].items():
            if hashlib.sha256(outer.read(filename)).hexdigest()!=entry['sha256']:raise ValueError('Frozen build hash mismatch')
    original=zipfile.ZipFile(io.BytesIO(outer.read('original_build.zip'))) if nested else outer
    nba='candidate_lineups.csv' in original.namelist()
    contest=json.loads(original.read('inputs/contest.json'))
    pool=pd.read_csv(io.BytesIO(original.read('inputs/player_pool.csv' if nba else 'player_pool.csv')))
    if nba:
        candidates=pd.read_csv(io.BytesIO(original.read('candidate_lineups.csv')),dtype=str)
        ids=dict(zip(pool['Player ID'].astype(str),pool.Name));candidates=candidates.apply(lambda col:col.map(ids))
        if candidates.isna().any().any():raise ValueError('Unknown NBA player ID')
        scores=pd.read_csv(io.BytesIO(original.read('candidate_scores.csv')))
        if len(candidates)!=len(scores):raise ValueError('Scored candidate alignment mismatch')
        candidates=pd.concat([candidates,scores],axis=1)
        candidates['_win']=candidates['Win %']/100;candidates['_top1']=candidates['Top 1%']/100;candidates['_prize']=candidates['Expected Prize ($)'];candidates['_mean']=candidates['Evaluation Mean Points']
        mode=next(key for key,slots in FORMATS.items() if key.startswith('nba') and all(s in candidates for s in slots))
        saved_manifest=json.loads(original.read('manifest.json'))
        for filename in ('inputs/settings.json','inputs/player_pool.csv','inputs/contest.json','candidate_lineups.csv','candidate_scores.csv','inputs/original_entries_salary.csv'):
            expected=saved_manifest['files'][filename]['sha256']
            if hashlib.sha256(original.read(filename)).hexdigest()!=expected:raise ValueError('Frozen NBA file hash mismatch: '+filename)
        settings=json.loads(original.read('inputs/settings.json'));diversity=float(settings['diversity'])
        pool.attrs['platform']='DraftKings' if mode=='nba_dk' else 'FanDuel'
        from simmah_nba_portfolio_limits import portfolio_limits
        limits=portfolio_limits(pool);controls={row.Name:limits[str(row['Player ID'])] for _,row in pool.iterrows()}
        tiers=[[r['first'],r['last'],r['prize']] for r in contest['payout_tiers']]
        template=original.read('inputs/original_entries_salary.csv')
        constraints='Current NBA hard limits derived from frozen pool (overall, minute and trusted-ownership caps); historical hidden manual overrides unavailable.'
    else:
        candidates=pd.read_csv(io.BytesIO(original.read('scored_lineups.csv')))
        mode=next(key for key,slots in FORMATS.items() if not key.startswith('nba') and all(s in candidates for s in slots))
        candidates['_win']=candidates.WinRate;candidates['_top1']=candidates.Top1;candidates['_prize']=candidates['Expected Prize ($)'];candidates['_mean']=candidates['SimMean']
        if not nested:raise ValueError('NFL comparison needs exact latest export/settings checkpoint')
        latest=zipfile.ZipFile(io.BytesIO(outer.read('latest_export_checkpoint.zip')))
        saved=json.loads(gzip.decompress(base64.b64decode(latest.read('workspace_snapshot.txt'))))['values']
        site='DraftKings' if mode.startswith('dk') else 'FanDuel'
        label={'dk_classic':'Classic','dk_showdown':'Showdown','fd_full':'Full Roster','fd_single':'Single Game'}[mode]
        diversity=float(saved['portfolio_exposure_diversity_'+site+'_'+label+'_v1'])
        controls=control_frame(saved['control_values' if site=='DraftKings' else 'fd_player_controls_'+label])
        tiers=contest['payouts'];template=latest.read('export.csv');constraints='Saved player controls and diversity; identical current selector for every method.'
    slots=FORMATS[mode];special=mode in ('dk_showdown','fd_single');fd='fd' in mode
    rows=list(csv.reader(io.StringIO(template.decode('utf-8-sig'))));header=[s.strip().lower() for s in rows[0]]
    entry_col=next(i for i,s in enumerate(header) if s in ('entry_id','entry id'));contest_col=next(i for i,s in enumerate(header) if s in ('contest_id','contest id'))
    own_ids=[row[entry_col] for row in rows[1:] if len(row)>max(entry_col,contest_col) and row[entry_col].isdigit() and row[contest_col]==str(contest['id'])]
    if not own_ids or len(own_ids)!=len(set(own_ids)):raise ValueError('Exact original entry identities required')
    selections=select_challengers(candidates,slots,len(own_ids),controls,diversity)
    # Actuals are deliberately loaded only after ALL challenge selections finish.
    standings_raw=Path(standings_path).read_bytes();frames=read_standings(standings_raw,Path(standings_path).name)
    if len(frames)!=1:raise ValueError('One completed standings table required')
    frame=frames[0];entries=frame.dropna(subset=['Rank','EntryId','Points']).copy();entries['_id']=entries.EntryId.astype('int64').astype(str)
    if entries._id.duplicated().any():raise ValueError('Duplicate standings entries')
    if 'TimeRemaining' in entries and not pd.to_numeric(entries.TimeRemaining).eq(0).all():raise ValueError('Unfinished results')
    if not set(own_ids)<=set(entries._id):raise ValueError('Original entry IDs absent from standings')
    opponents=entries.loc[~entries._id.isin(own_ids),'Points'].to_numpy(float);actual={}
    for record in frame.dropna(subset=['Player','FPTS']).to_dict('records'):
        if mode=='dk_showdown' and record.get('Roster Position')=='CPT':continue
        label=str(record['Player']);match=re.search(r'\((\d+(?:-\d+)?)\)\s*$',label)
        if nba and match:label=ids.get(match.group(1),label)
        key=name_key(label);points=float(record['FPTS'])
        if not np.isfinite(points) or (key in actual and abs(actual[key]-points)>.001):raise ValueError('Invalid/conflicting actuals')
        actual[key]=points
    for row in pool.to_dict('records'):
        if str(row.get('Position','')).upper() in {'DST','D','DEF'}:
            full=name_key(row['Name']);short=name_key(str(row['Name']).split()[-1])
            if short in actual and full not in actual:actual[full]=actual[short]
    all_points,all_supported=score_candidates(candidates,slots,actual,special)
    signal={}
    signal_columns={'top1':'_top1','win_rate':'_win','expected_prize':'_prize','mean_points':'_mean'}
    if 'Lineup Ownership Score (%)' in candidates:
        candidates['_inverse_ownership_sum']=-pd.to_numeric(candidates['Lineup Ownership Score (%)'])
        signal_columns['inverse_ownership_sum_proxy']='_inverse_ownership_sum'
    population=candidates.loc[all_supported].copy();population['_actual']=all_points[all_supported]
    if len(population)>1:
        k=max(1,int(np.ceil(.05*len(population))))
        actual_elite=population._actual.ge(population._actual.nlargest(k).iloc[-1])
        for name,column in signal_columns.items():
            values=pd.to_numeric(population[column],errors='coerce')
            usable=values.notna()
            chosen=values.nlargest(k).index
            signal[name]={'scored_candidates':len(population),'spearman_score_vs_actual_points':float(values[usable].corr(population.loc[usable,'_actual'],method='spearman')) if values[usable].nunique()>1 else None,
                'pregame_top5_count':len(chosen),'hindsight_top5_count_including_ties':int(actual_elite.sum()),
                'overlap_count':int(actual_elite.loc[chosen].sum()),'precision_in_pregame_top5':float(actual_elite.loc[chosen].mean()),
                'random_precision_baseline':float(actual_elite.mean()),
                'scope':'Conditional diagnostic among fully scored candidates; never used to filter challenger selection.'}
    fees=len(own_ids)*float(contest['entry_fee']);methods={}
    for method,item in selections.items():
        if 'error' in item:methods[method]=item;continue
        selected=item['portfolio'];points,supported=score_candidates(selected,slots,actual,special)
        missing=sorted({name for row in selected[slots].itertuples(index=False,name=None) for name in row if name_key(name) not in actual})
        record={'entries':len(selected),'fully_scored_entries':int(supported.sum()),'missing_published_scores':missing,'effective_automatic_cap':item['effective_automatic_cap']}
        if supported.all():
            ranks,prizes=joint_prizes(points,opponents,tiers)
            record.update(estimated_joint_prizes=float(prizes.sum()),fees=fees,estimated_net=float(prizes.sum()-fees),cashed_entries=int((prizes>0).sum()),best_rank=int(ranks.min()),mean_actual_points=float(points.mean()))
        else:record.update(estimated_joint_prizes=None,fees=fees,estimated_net=None,status='Incomplete actuals: entire portfolio return is unknown; no lineup dropped or zero-filled')
        methods[method]=record
    return {'schema':1,'sport':'NBA' if nba else 'NFL','format':mode,'contest_id':str(contest['id']),
       'build_sha256':hashlib.sha256(raw).hexdigest(),'standings_sha256':hashlib.sha256(standings_raw).hexdigest(),
       'selector_version':SELECTION_VERSION,'constraint_scope':constraints,'diversity':diversity,'original_entries_removed':len(own_ids),
       'candidate_count':len(candidates),'fully_scored_candidates':int(all_supported.sum()),'metric_signal_diagnostics':signal,'methods':methods,'promotion_accepted':False,
       'limitations':['Retrospective challenger comparison; these outcomes were already inspected, so no prospective validation is claimed.',
          'Actuals never enter selection; candidates are not filtered using outcome availability.',
          'All methods use identical candidate pools and constraints, but realized exposures can differ.',
          'Current shared selector is used for all challengers; this is not an exact replay of older selector implementations.',
          'Estimated prizes include all selected entries and opponent ties; not an account statement or evidence of future profit.',
          'No live method activated; independent later slate validation is still required.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build',required=True);parser.add_argument('--standings',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();report=compare(args.build,args.standings);path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
