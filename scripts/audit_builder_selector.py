"""Offline NFL/NBA frozen candidate-builder versus portfolio-selector diagnosis.

Actuals score saved rosters only; they never generate or select a new portfolio.
Hindsight best candidates are opportunity diagnostics, not attainable ROI claims.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import unicodedata
import zipfile
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_contest_history import name_key as base_name_key, read_standings

def name_key(value):
    return base_name_key(unicodedata.normalize("NFKD",str(value)).encode("ascii","ignore").decode())

FORMATS = {'nba_dk':['PG','SG','SF','PF','C','G','F','UTIL'],
 'nba_fd':['PG','SG','SF','PF','C','GF','FC','UTIL1','UTIL2'],'dk_showdown':['Captain','Flex1','Flex2','Flex3','Flex4','Flex5'],
 'fd_single':['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5'],
 'dk_classic':['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','DST'],
 'fd_full':['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','D']}


def canonical(names,special):
    normalized=[name_key(n) for n in names]
    return ((normalized[0],)+tuple(sorted(normalized[1:]))) if special else tuple(sorted(normalized))


def score_candidates(frame,slots,actual,special):
    scores=[];supported=[]
    for row in frame[slots].itertuples(index=False,name=None):
        keys=[name_key(n) for n in row]
        valid=len(keys)==len(set(keys)) and all(k in actual for k in keys)
        supported.append(valid)
        scores.append(round(sum(actual[k]*(1.5 if special and i==0 else 1.) for i,k in enumerate(keys)),2) if valid else None)
    return np.array(scores,float),np.array(supported,bool)


def standalone_metrics(points,opponents,tiers):
    """Insert ONE hypothetical candidate against opponents excluding own entries.

    Ties share the occupied payout positions. These single-entry comparisons
    cannot be summed into a replacement portfolio return.
    """
    values=np.sort(np.rint(np.asarray(opponents)*100).astype(np.int64))
    p=np.rint(np.asarray(points)*100).astype(np.int64)
    greater=len(values)-np.searchsorted(values,p,side='right')
    equal=np.searchsorted(values,p,side='right')-np.searchsorted(values,p,side='left')
    ranks=greater+1
    payout=np.zeros(max(len(values)+2,max(b for a,b,prize in tiers)+2))
    for a,b,prize in tiers:payout[a:b+1]=float(prize)
    prefix=np.r_[0,np.cumsum(payout)]
    prizes=(prefix[ranks+equal+1]-prefix[ranks])/(equal+1)
    return ranks,prizes


def error_metrics(rows):
    frame=pd.DataFrame(rows)
    if frame.empty:return {'rows':0}
    error=frame.prediction-frame.actual
    return {'rows':len(frame),'mae':float(error.abs().mean()),'rmse':float(np.sqrt((error**2).mean())),
            'bias_prediction_minus_actual':float(error.mean())}


def grouped_errors(rows):
    result={}
    for key in ('position','projection_source','projection_band','projected_minutes_band'):
        groups={}
        for row in rows:groups.setdefault(str(row[key]),[]).append(row)
        result[key]={name:error_metrics(values) for name,values in sorted(groups.items())}
    return result


def audit(build_path,standings_path):
    build_raw=Path(build_path).read_bytes();standings_raw=Path(standings_path).read_bytes()
    outer=zipfile.ZipFile(io.BytesIO(build_raw))
    nested='original_build.zip' in outer.namelist()
    if nested:
        manifest=json.loads(outer.read('manifest.json'))
        for filename,info in manifest['files'].items():
            if hashlib.sha256(outer.read(filename)).hexdigest()!=info['sha256']:raise ValueError('Nested build hash mismatch')
    original=zipfile.ZipFile(io.BytesIO(outer.read('original_build.zip'))) if nested else outer
    contest=json.loads(original.read('inputs/contest.json'))
    nba='candidate_lineups.csv' in original.namelist()
    candidates=pd.read_csv(io.BytesIO(original.read('candidate_lineups.csv' if nba else 'candidates.csv')),dtype=str if nba else None)
    pool=pd.read_csv(io.BytesIO(original.read('inputs/player_pool.csv' if nba else 'player_pool.csv')))
    if nba:
        player_ids=dict(zip(pool['Player ID'].astype(str),pool.Name))
        candidates=candidates.apply(lambda column:column.map(player_ids))
        if candidates.isna().any().any():raise ValueError('Unknown NBA candidate player ID')
        scored=pd.concat([candidates,pd.read_csv(io.BytesIO(original.read('candidate_scores.csv')))],axis=1)
        scored['Top1']=scored['Top 1%']/100
        contest['payouts']=[[row['first'],row['last'],row['prize']] for row in contest['payout_tiers']]
    else:scored=pd.read_csv(io.BytesIO(original.read('scored_lineups.csv')))

    mode=next((key for key,slots in FORMATS.items() if all(slot in candidates for slot in slots)),None)
    if mode is None:raise ValueError('Unsupported roster columns')
    if len(candidates)!=len(scored):raise ValueError('Candidate/scored row counts differ')
    slots=FORMATS[mode];special=mode in ('dk_showdown','fd_single')
    platform='DraftKings' if mode.startswith('dk') or mode=='nba_dk' else 'FanDuel'
    frames=read_standings(standings_raw,Path(standings_path).name)
    if len(frames)!=1:raise ValueError('Exactly one standings table required')
    frame=frames[0]
    entries=frame.dropna(subset=['Rank','EntryId','Points']).copy()
    if 'TimeRemaining' in entries and not pd.to_numeric(entries.TimeRemaining).eq(0).all():raise ValueError('Contest not complete')
    entries['_id']=entries.EntryId.astype('int64').astype(str)
    if entries._id.duplicated().any():raise ValueError('Duplicate entry IDs')
    actual={}
    for record in frame.dropna(subset=['Player','FPTS']).to_dict('records'):
        if mode=='dk_showdown' and record.get('Roster Position')=='CPT':continue
        label=str(record['Player'])
        match=re.search(r'\((\d+(?:-\d+)?)\)\s*$',label)
        if match and nba:
            label=player_ids.get(match.group(1),label)
        key=name_key(label);points=float(record['FPTS'])
        if not np.isfinite(points):raise ValueError('Nonfinite actual score')
        if key in actual and abs(actual[key]-points)>.001:raise ValueError('Conflicting base scores')
        actual[key]=points
    # Exact, unique short DST aliases are derived from the supplied pool, not fuzzy names.
    aliases={}
    for player in pool.to_dict('records'):
        if str(player.get('Position','')).upper() in {'D','DST','DEF'}:
            short=name_key(str(player['Name']).split()[-1]);full=name_key(player['Name'])
            if short in aliases and aliases[short]!=full:raise ValueError('Ambiguous defense alias')
            aliases[short]=full
    for short,full in aliases.items():
        if short in actual and full not in actual:actual[full]=actual[short]
    keys=[canonical(row,special) for row in candidates[slots].itertuples(index=False,name=None)]
    if len(keys)!=len(set(keys)):raise ValueError('Candidate pool contains canonical duplicates')
    scored_map={canonical(row,special):i for i,row in enumerate(scored[slots].itertuples(index=False,name=None))}
    if len(scored_map)!=len(scored):raise ValueError('Scored candidates contain duplicates')
    if set(keys)!=set(scored_map):raise ValueError('Built/scored candidate roster sets differ')
    ranked=scored.iloc[[scored_map[k] for k in keys]].reset_index(drop=True)
    selected_keys=[];selected_names=[];own_ids=[];roster_matches=0;submitted_points=[]
    if nested and 'latest_export_checkpoint.zip' in outer.namelist():
        latest=zipfile.ZipFile(io.BytesIO(outer.read('latest_export_checkpoint.zip')))
        csv_rows=list(csv.reader(io.StringIO(latest.read('export.csv').decode('utf-8-sig'))))
        fd=platform=='FanDuel';id_column=1 if fd else 2
        targets=[row for row in csv_rows[1:] if len(row)>=4+len(slots) and row[0].isdigit() and row[id_column]==str(contest['id'])]
        for row in targets:
            if fd:
                ids=dict(zip(pool['Player ID' if nba else 'FD_ID'].astype(str),pool.Name))
                names=[ids[value] for value in row[4:4+len(slots)]]
            else:
                id_column_name='Player ID' if nba else 'DK_ID'
                ids=dict(zip(pool[id_column_name].astype(str),pool.Name)) if id_column_name in pool else {}
                names=[ids.get(value,re.sub(r' \(\d+\)$','',value)) for value in row[4:4+len(slots)]]
            selected_names.append(names);selected_keys.append(canonical(names,special));own_ids.append(row[0])
        if len(set(own_ids))!=len(own_ids):raise ValueError('Duplicate exported IDs')
        found=entries.set_index('_id').loc[own_ids]
        for names,(_,row) in zip(selected_names,found.iterrows()):
            tokens=re.findall(r'\b(?:CPT|MVP|ANYFLEX|FLEX|DST|DEF|UTIL1|UTIL2|UTIL|PG|SG|SF|PF|GF|FC|QB|RB|WR|TE|K|C|G|F|D)\s+(.+?)(?=\s+(?:CPT|MVP|ANYFLEX|FLEX|DST|DEF|UTIL1|UTIL2|UTIL|PG|SG|SF|PF|GF|FC|QB|RB|WR|TE|K|C|G|F|D)\s+|$)',str(row.Lineup))
            parsed_names=[name.strip(' ,;') for name in tokens]
            expected=canonical(names,special)
            observed=canonical(parsed_names,special)
            observed=tuple(aliases.get(key,key) for key in observed)
            if not special:observed=tuple(sorted(observed))
            roster_matches+=observed==expected
        submitted_points=found.Points.astype(float).tolist()
        selected_frame=pd.DataFrame(selected_names,columns=slots)
        calculated,complete=score_candidates(selected_frame,slots,actual,special)
        if complete.all() and roster_matches==len(selected_names) and not np.allclose(calculated,found.Points.to_numpy(float),atol=.03):raise ValueError('Selected scores do not reconstruct')
    selection_evidence=('downloaded export; all rosters match final standings' if roster_matches==len(own_ids) else 'downloaded export differs from some final entered rosters; evaluate frozen selection separately') if own_ids else 'no final export available'
    if nba and not selected_names and 'portfolio_at_build.csv' in original.namelist():
        saved=pd.read_csv(io.BytesIO(original.read('portfolio_at_build.csv')),dtype={slot:str for slot in slots})
        selected_names=[[player_ids[str(row[slot])] for slot in slots] for _,row in saved.iterrows()]
        selected_keys=[canonical(row,False) for row in selected_names]
        selection_evidence='build-time portfolio only; final submission and own entry identities unverified'
    opponents=entries.loc[~entries._id.isin(own_ids),'Points'].to_numpy(float)
    actual_points,supported=score_candidates(candidates,slots,actual,special)
    valid=np.flatnonzero(supported)
    if not len(valid):raise ValueError('No fully scored candidates')
    ranks,prizes=standalone_metrics(actual_points[valid],opponents,contest['payouts'])
    by_key={keys[index]:pos for pos,index in enumerate(valid)}
    order=np.argsort(-actual_points[valid],kind='stable');best=int(order[0]);best_index=valid[best]
    top1=ranks<=math.ceil((len(opponents)+1)*.01)
    top10=ranks<=math.ceil((len(opponents)+1)*.1)
    pregame_top1=pd.to_numeric(ranked.Top1).to_numpy(float) if 'Top1' in ranked else None
    pregame_order=np.argsort(-pregame_top1,kind='stable') if pregame_top1 is not None else None
    pregame_ranks=np.empty(len(keys),int)
    if pregame_order is not None:pregame_ranks[pregame_order]=np.arange(1,len(keys)+1)
    selected_positions=[by_key[k] for k in selected_keys if k in by_key]
    missing_selected=[name for row in selected_names for name in row if name_key(name) not in actual]
    sorted_actual=np.sort(np.rint(actual_points[valid]*100).astype(np.int64))
    hindsight_rank=len(valid)-np.searchsorted(sorted_actual,np.rint(actual_points[valid]*100).astype(np.int64),side='right')+1
    selected_summary=None
    if selected_positions:
        selected_summary={'entries':len(selected_keys),'fully_scored_saved_candidates':len(selected_positions),'unscored_or_outside_pool_entries':len(selected_keys)-len(selected_positions),'missing_published_player_scores':sorted(set(missing_selected)),'all_match_saved_candidates':all(k in keys for k in selected_keys),'final_standings_roster_matches':roster_matches if own_ids else None,'final_entered_best_points':max(submitted_points) if submitted_points else None,
          'best_actual_points':float(max(actual_points[valid][selected_positions])),
          'best_standalone_rank':int(min(ranks[selected_positions])),
          'top1_entries':int(top1[selected_positions].sum()),'top10_entries':int(top10[selected_positions].sum()),
          'positive_prize_standalone_entries':int((prizes[selected_positions]>0).sum()),
          'best_hindsight_candidate_rank':int(min(hindsight_rank[selected_positions])),
          'median_hindsight_candidate_rank':float(np.median(hindsight_rank[selected_positions])),
          'hindsight_top20_candidates_selected':int(sum(hindsight_rank[pos]<=20 for pos in selected_positions)),
          'mean_saved_top1_probability':float(pregame_top1[[keys.index(k) for k in selected_keys if k in keys]].mean()) if pregame_top1 is not None and any(k in keys for k in selected_keys) else None}
    player_rows=[]
    for row in pool.to_dict('records'):
        key=name_key(row['Name']);prediction=pd.to_numeric(row.get('Projection'),errors='coerce')
        if key not in actual or not np.isfinite(prediction):continue
        player_rows.append({'player':row['Name'],'position':row.get('Position','Unknown'),
          'projection_source':row.get('ProjectionSource',row.get('Projection Source','Unknown')),'prediction':float(prediction),'actual':actual[key],
          'projection_band':'under 5' if prediction<5 else '5 to under 10' if prediction<10 else '10 to under 20' if prediction<20 else '20+',
          'projected_minutes_band':('unknown' if pd.isna(row.get('Projected Minutes')) else 'under 16' if float(row['Projected Minutes'])<16 else '16 to under 28' if float(row['Projected Minutes'])<28 else '28+'),'error':float(prediction)-actual[key]})
    report={'schema':1,'platform':platform,'format':mode,'contest_id':str(contest['id']),
      'source_hashes':{'build':hashlib.sha256(build_raw).hexdigest(),'standings':hashlib.sha256(standings_raw).hexdigest()},
      'sport':'NBA' if nba else 'NFL','selection_evidence':selection_evidence,'scored_entries_in_reference':len(entries),'opponents_after_removing_exported_entries':len(opponents),
      'candidate_pool':{'saved':len(candidates),'fully_scored':int(supported.sum()),'unscored_missing_actuals':int((~supported).sum()),
        'missing_actual_players_by_candidate_count':dict(Counter(name for row in candidates[slots].itertuples(index=False,name=None) for name in row if name_key(name) not in actual).most_common()),'actual_top1_candidates':int(top1.sum()),'actual_top10_candidates':int(top10.sum()),'positive_prize_candidates':int((prizes>0).sum())},
      'hindsight_best_single_candidate':{'points':float(actual_points[best_index]),'standalone_rank':int(ranks[best]),
        'standalone_prize':float(prizes[best]),'pregame_top1_rank':int(pregame_ranks[best_index]) if pregame_order is not None else None,
        'roster':dict(zip(slots,candidates.iloc[best_index][slots].tolist()))},
      'exported_portfolio':selected_summary,'player_errors':{'overall':error_metrics(player_rows),'groups':grouped_errors(player_rows),
        'largest_absolute_errors':sorted(player_rows,key=lambda row:abs(row['error']),reverse=True)[:10]},
      'limitations':['Hindsight scores diagnose builder coverage and selection opportunity; they cannot select future lineups. Candidate ranks give tied scores the same first rank.',
        'Single-candidate ranks remove all exported own entries then insert one candidate; these prizes are not joint portfolio returns.',
        'Exposure/stack/uniqueness constraints may prevent combining hindsight best candidates into a legal portfolio.',
        'Missing player actuals stay unknown; unsupported candidates are excluded, never zero-filled.',
        'Entry rows retain published points even when their lineup text is blank. Standings scores are user-asserted final.',
        'No model parameters, rankings or candidate generation changed.']}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',required=True);parser.add_argument('--standings',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();report=audit(args.build,args.standings)
    destination=Path(args.output);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('player_errors','limitations')},indent=2))

if __name__=='__main__':main()
