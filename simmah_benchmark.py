"""Offline DK Classic replay audit. No Streamlit, network, or live data reads.

Freeze an evidence bundle, verify its hashes on every run, then evaluate saved
portfolios against completed standings. Outcomes never select or alter lineups.
A replay audit is not a new build or evidence of out-of-sample profitability.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import time
import zipfile
from collections import Counter

import numpy as np
import pandas as pd
from simmah_candidates import offense_vs_defense_allowed
from simmah_contests import payout_vector
from simmah_qb_roles import quarterback_conflicts

VERSION = 'dk-classic-audit-v1'
SLOTS = ['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','DST']
REQUIRED_FILES = {'players':'players.csv','portfolio':'portfolio.csv','field':'field.csv',
                  'standings':'standings.zip','contest':'contest.json'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def freeze_bundle(files, destination):
    """Copy supplied evidence once; never fetch, rewrite, or infer missing data."""
    if set(files) != set(REQUIRED_FILES):
        raise ValueError('Bundle requires players, portfolio, field, standings and contest')
    payload = {key:Path(path).read_bytes() for key,path in files.items()}
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    entries = {}
    for key,raw in payload.items():
        filename = REQUIRED_FILES[key]
        (root/filename).write_bytes(raw)
        entries[key] = {'file':filename,'sha256':digest(raw),'bytes':len(raw),
                        'role':'evaluation_only' if key=='standings' else 'supplied_evidence'}
    manifest = {'schema':1,'files':entries,
                'fingerprint':digest(json.dumps(entries,sort_keys=True).encode()),
                'pregame_timestamp_verified':False}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def load_bundle(root):
    root = Path(root)
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest.get('schema') != 1 or set(manifest.get('files',{})) != set(REQUIRED_FILES):
        raise ValueError('Invalid evidence bundle manifest')
    entries = manifest['files']
    if manifest['fingerprint'] != digest(json.dumps(entries,sort_keys=True).encode()):
        raise ValueError('Manifest fingerprint mismatch')
    payload = {}
    for key,entry in entries.items():
        if entry['file'] != REQUIRED_FILES[key]:
            raise ValueError('Unexpected bundle file path')
        raw = (root/entry['file']).read_bytes()
        if digest(raw) != entry['sha256'] or len(raw) != entry['bytes']:
            raise ValueError('Frozen evidence changed: '+key)
        payload[key] = raw
    return manifest,payload


def validate_players(players):
    required = {'Name','Team','Opponent','Position','Salary','Projection'}
    if not required <= set(players):raise ValueError('Player inputs missing required columns')
    if players.Name.isna().any() or players.Name.astype(str).str.strip().eq('').any():
        raise ValueError('Empty player names')
    if players.Name.duplicated().any():raise ValueError('Ambiguous duplicate player names')
    for column in ['Salary','Projection']:
        values = pd.to_numeric(players[column],errors='coerce')
        if not np.isfinite(values).all() or (values<=0).any():
            raise ValueError('Player '+column+' must be finite and positive')
    return players.set_index('Name').to_dict('index')


def audit_rosters(frame, metadata, avoid_opposing_defense):
    if not set(SLOTS+['Salary']) <= set(frame):raise ValueError('Incomplete Classic roster columns')
    errors = Counter();keys=[];groups=Counter()
    for record in frame.to_dict('records'):
        names = [record[slot] for slot in SLOTS]
        keys.append(tuple(sorted(map(str,names))))
        if len(set(names)) != 9:errors['repeated_player']+=1
        if any(name not in metadata for name in names):
            errors['unknown_player']+=1;continue
        for slot,name in zip(SLOTS,names):
            positions=set(str(metadata[name]['Position']).upper().split('/'))
            allowed={'RB','WR','TE'} if slot=='FLEX' else {'DST','D','DEF'} if slot=='DST' else {slot.rstrip('123')}
            if not positions & allowed:errors['position']+=1
        salary=sum(float(metadata[name]['Salary']) for name in names)
        if salary>50000 or salary<=0:errors['salary_cap']+=1
        if abs(salary-float(record['Salary']))>.01:errors['salary_sum']+=1
        teams=Counter(metadata[name]['Team'] for name in names)
        if max(teams.values())>8 or len(teams)<2:errors['team_limit']+=1
        if avoid_opposing_defense and not offense_vs_defense_allowed({s:record[s] for s in SLOTS},metadata):
            errors['offense_against_defense']+=1
        qb=metadata[record['QB']]
        stack=sum(metadata[name]['Team']==qb['Team'] and metadata[name]['Position'] in {'WR','TE'} for name in names[1:8])
        back=any(metadata[name]['Team']==qb['Opponent'] for name in names[1:8])
        groups[str(min(stack,2)*2+int(back))]+=1
    copies=Counter(keys)
    return {'rows':len(frame),'unique_rosters':len(copies),'max_copies':max(copies.values(),default=0),
            'violations':dict(errors),'construction_groups':dict(sorted(groups.items()))}


def read_completed_standings(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        csvs=[name for name in archive.namelist() if name.lower().endswith('.csv')]
        if len(csvs)!=1:raise ValueError('Standings ZIP must contain exactly one CSV')
        records=list(csv.DictReader(io.StringIO(archive.read(csvs[0]).decode('utf-8-sig'))))
    if not records:raise ValueError('Empty standings')
    if any(str(row.get('TimeRemaining','')).strip() not in {'0','0.0'} for row in records):
        raise ValueError('Standings are not verified complete')
    ids=[row.get('EntryId') for row in records]
    if not all(ids) or len(set(ids))!=len(ids):raise ValueError('Missing or duplicate contest entry IDs')
    scores={}
    for row in records:
        name=str(row.get('Player','')).strip();value=row.get('FPTS','')
        if name and value!='':
            value=float(value)
            if not np.isfinite(value):raise ValueError('Invalid actual player score')
            if name in scores and abs(scores[name]-value)>.001:raise ValueError('Conflicting player scores')
            scores[name]=value
    return records,scores


def completed_scores(frame, scores):
    supported=frame[SLOTS].isin(set(scores)).all(axis=1)
    values=frame.loc[supported,SLOTS].map(scores.get).sum(axis=1).round(2).to_numpy()
    return values,supported


def replace_portfolio(records, frame, scores, contest):
    """Remove the owner's original entries and insert the whole new portfolio.

    All own and opponent ties split the occupied payout positions together.
    Blank opponent roster strings still retain their official entry and score.
    """
    owner=str(contest['owner']).strip()
    if not owner:raise ValueError('Contest owner is required')
    pattern=re.compile(r'^'+re.escape(owner)+r'(?:\s+\(\d+/\d+\))?$',re.I)
    owned=[bool(pattern.fullmatch(str(row.get('EntryName','')).strip())) for row in records]
    if sum(owned)!=len(frame):raise ValueError('Replacement count does not match original owner entries')
    values,supported=completed_scores(frame,scores)
    if not supported.all():raise ValueError('Actual player scores missing; zero substitution is disabled')
    opponents=np.round(np.array([float(row['Points']) for row,own in zip(records,owned) if not own]),2)
    if not np.isfinite(opponents).all():raise ValueError('Invalid opponent scores')
    if int(contest['field_size'])!=len(records):raise ValueError('Contest field size does not match standings')
    fee=float(contest['entry_fee'])
    if not np.isfinite(fee) or fee<=0:raise ValueError('Entry fee must be positive')
    payouts=payout_vector(len(records),contest['payouts']);prefix=np.r_[0.,np.cumsum(payouts)]
    output=[]
    for value in values:
        better=int((opponents>value).sum()+(values>value).sum())
        ties=int((opponents==value).sum()+(values==value).sum())
        first,last=better+1,better+ties
        prize=float((prefix[last]-prefix[first-1])/ties)
        output.append({'score':float(value),'rank':first,'tied_entries':ties,'prize':prize})
    winnings=sum(row['prize'] for row in output);cost=fee*len(frame)
    return {'entries':len(frame),'entry_fees':cost,'winnings':round(winnings,6),
            'net':round(winnings-cost,6),'roi_pct':round(100*(winnings/cost-1),6),
            'cashing_entries':sum(row['prize']>0 for row in output),
            'mean_score':float(values.mean()),'best_score':float(values.max()),
            'best_rank':min(row['rank'] for row in output),'lineups':output}


def projection_baseline(players, count, salary_min=48000, max_exposure_pct=80):
    """Sequential exact projection maximizers, with unique rosters and exposure caps.

    Uses only the supplied pregame player table. No stacks, outcomes, ownership,
    historical contest profiles, or player identity exceptions enter the solve.
    This is an explicit comparison policy, not the simulation portfolio policy.
    """
    from scipy.optimize import milp,Bounds,LinearConstraint
    from scipy.sparse import csc_matrix
    metadata=validate_players(players)
    names=players.Name.astype(str).to_numpy();positions=players.Position.astype(str).str.upper().to_numpy()
    positions=np.where(np.isin(positions,['D','DEF']),'DST',positions)
    if not set(positions)<={'QB','RB','WR','TE','DST'}:
        raise ValueError('Projection baseline v1 requires single-position DK Classic players')
    salary=players.Salary.to_numpy(float);projection=players.Projection.to_numpy(float)
    teams=players.Team.astype(str).to_numpy();opponents=players.Opponent.astype(str).to_numpy()
    matrix=[np.ones(len(players)),salary];lower=[9,salary_min];upper=[9,50000]
    for position,lo,hi in [('QB',1,1),('DST',1,1),('RB',2,3),('WR',3,4),('TE',1,2)]:
        matrix.append((positions==position).astype(float));lower.append(lo);upper.append(hi)
    for team in np.unique(teams):
        matrix.append((teams==team).astype(float));lower.append(0);upper.append(8)
    for defense in np.flatnonzero(positions=='DST'):
        facing=((teams==opponents[defense]) | (opponents==teams[defense])) & (positions!='DST')
        row=facing.astype(float);row[defense]=8
        matrix.append(row);lower.append(0);upper.append(8)
    if not 0<max_exposure_pct<=100 or int(count)<1:raise ValueError('Invalid baseline portfolio settings')
    capacity=max(1,int(np.floor(count*max_exposure_pct/100)));used=np.zeros(len(players),int)
    rows=[]
    for _ in range(int(count)):
        solve=milp(-projection,integrality=np.ones(len(players)),bounds=Bounds(np.zeros(len(players)),(used<capacity).astype(float)),
            constraints=LinearConstraint(csc_matrix(np.asarray(matrix)),np.asarray(lower),np.asarray(upper)),
            options={'time_limit':5.,'mip_rel_gap':0.})
        if solve.status!=0 or solve.x is None:
            raise ValueError('Projection baseline did not reach a proven optimum: '+str(solve.message))
        picks=np.flatnonzero(solve.x>.5);used[picks]+=1
        selected={p:[int(i) for i in picks if positions[i]==p] for p in ['QB','RB','WR','TE','DST']}
        row={'QB':names[selected['QB'].pop()], 'DST':names[selected['DST'].pop()]}
        for position,slots in [('RB',['RB1','RB2']),('WR',['WR1','WR2','WR3']),('TE',['TE'])]:
            for slot in slots:row[slot]=names[selected[position].pop()]
        remaining=[i for position in ['RB','WR','TE'] for i in selected[position]]
        if len(remaining)!=1:raise ValueError('Invalid baseline flex assignment')
        row['FLEX']=names[remaining[0]];row['Salary']=int(salary[picks].sum());row['External Projection']=float(projection[picks].sum())
        rows.append(row)
        exclude=np.zeros(len(players));exclude[picks]=1;matrix.append(exclude);lower.append(0);upper.append(8)
    result=pd.DataFrame(rows)
    if audit_rosters(result,metadata,True)['violations']:raise ValueError('Baseline roster verification failed')
    return result


def run_audit(root, include_baseline=False):
    started=time.perf_counter();manifest,raw=load_bundle(root);times={}
    players=pd.read_csv(io.BytesIO(raw['players']));portfolio=pd.read_csv(io.BytesIO(raw['portfolio']))
    field=pd.read_csv(io.BytesIO(raw['field']));contest=json.loads(raw['contest'])
    if contest.get('format')!='DraftKings Classic':raise ValueError('Only DK Classic is supported in benchmark v1')
    metadata=validate_players(players)
    portfolio_rules=audit_rosters(portfolio,metadata,True)
    field_rules=audit_rosters(field,metadata,False)
    times['input_validation_seconds']=time.perf_counter()-started
    baseline=None
    if include_baseline:
        mark=time.perf_counter()
        baseline=projection_baseline(players,len(portfolio))
        times['projection_baseline_build_seconds']=time.perf_counter()-mark
    # Only now open actual outcomes; this tool never builds/ranks/selects lineups.
    mark=time.perf_counter();records,scores=read_completed_standings(raw['standings'])
    result=replace_portfolio(records,portfolio,scores,contest)
    baseline_result=replace_portfolio(records,baseline,scores,contest) if baseline is not None else None
    times['completed_contest_evaluation_seconds']=time.perf_counter()-mark
    field_values,supported=completed_scores(field,scores)
    valid_actual=[float(row['Points']) for row in records if row.get('Lineup','').strip()]
    conflicts=quarterback_conflicts(players)
    blockers=[]
    if conflicts:blockers.append('Same-team projected quarterbacks lack saved starter confirmation')
    if not manifest.get('pregame_timestamp_verified'):blockers.append('Pregame input timestamp provenance not independently verified')
    if portfolio_rules['violations'] or field_rules['violations']:blockers.append('Roster validation failures')
    if 'Projected Ownership' not in players:blockers.append('Projected ownership snapshot missing')
    times['audit_total_seconds']=time.perf_counter()-started
    return {'version':VERSION,'evidence_fingerprint':manifest['fingerprint'],
        'code_sha256':digest(Path(__file__).read_bytes()),'mode':'saved-portfolio diagnostic only',
        'fresh_build_ready':not blockers,'fresh_build_blockers':blockers,'quarterback_conflicts':conflicts,
        'portfolio_rules':portfolio_rules,'field_rules':field_rules,'actual_result':result,
        'projection_baseline':baseline_result,
        'projection_baseline_policy':{'salary_min':48000,'salary_max':50000,'max_player_exposure_pct':80,
            'unique_rosters':True,'opposing_defense_excluded':True,'stacks_required':False,
            'note':'Sequential projection-optimal roster selection; fixed policy, no outcome-based tuning'} if baseline is not None else None,
        'field_actual_scores':{'supported_rows':int(supported.sum()),'excluded_rows':int((~supported).sum()),
            'mean':float(field_values.mean()) if len(field_values) else None},
        'real_field_actual_mean':float(np.mean(valid_actual)) if valid_actual else None,
        'reported_simulated_roi_pct':float(portfolio['Expected ROI (%)'].mean()) if 'Expected ROI (%)' in portfolio else None,
        'timings':times,'limitations':['No fresh simulation was run',
            'Projection baseline runs only when explicitly requested',
            'No distributions can be reconstructed from lineup means alone',
            'This audit does not establish independent holdout performance']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    freeze=sub.add_parser('freeze')
    for key in REQUIRED_FILES:freeze.add_argument('--'+key,required=True)
    freeze.add_argument('--destination',required=True)
    audit=sub.add_parser('audit');audit.add_argument('bundle');audit.add_argument('--output',required=True);audit.add_argument('--projection-baseline',action='store_true')
    args=parser.parse_args()
    if args.command=='freeze':
        manifest=freeze_bundle({key:getattr(args,key) for key in REQUIRED_FILES},args.destination)
        print(json.dumps({'fingerprint':manifest['fingerprint'],'destination':args.destination},indent=2))
    else:
        result=run_audit(args.bundle,args.projection_baseline)
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print(json.dumps({key:result[key] for key in ['fresh_build_ready','fresh_build_blockers','actual_result','timings']},indent=2))


if __name__=='__main__':main()
