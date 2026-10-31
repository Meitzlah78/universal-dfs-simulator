"""Offline, in-sample duplicate-band trial on saved NFL single-game packages."""
import argparse
from collections import Counter
import hashlib
from itertools import combinations
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from simmah_contest_history import name_key
from simmah_slate_replay import canonical, parse_roster, _standings, official_scores, published_player_scores
from simmah_joint_field import (single_game_features, observed_duplicate_curve,
    fit_joint_field, JointFitNotConverged, DUPLICATE_BANDS)


def file_hash(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def atomic_report(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name);json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def run(package,standings_path,username,excluded_players,output,max_iterations=500):
    started=time.monotonic()
    with zipfile.ZipFile(package) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        def member(name):
            raw=archive.read(name);expected=manifest['files'][name]
            if len(raw)!=expected['bytes'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']:
                raise ValueError('Package integrity failed: '+name)
            return raw
        pool=pd.read_csv(io.BytesIO(member('player_pool.csv')))
        candidates=pd.read_csv(io.BytesIO(member('candidates.csv')))
        field=pd.read_csv(io.BytesIO(member('opponent_field.csv')))
    dk=manifest['format']=='DraftKings Showdown'
    if not dk and manifest['format']!='FanDuel Single Game':raise ValueError('Single-game package required')
    slots=['Captain','Flex1','Flex2','Flex3','Flex4','Flex5'] if dk else ['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5']
    candidate_keys=[canonical(row) for row in candidates[slots].itertuples(index=False,name=None)]
    field_keys=[canonical(row) for row in field[slots].itertuples(index=False,name=None)]
    metadata={name_key(row['Name']):row for row in pool.to_dict('records')}
    excluded={name_key(player) for player in excluded_players}
    for key in candidate_keys+field_keys:
        if excluded.intersection((key[0],*key[1])):raise ValueError('Excluded player remains in support')
        special,flex=key
        salary=(metadata[special].get('CaptainSalary',1.5*metadata[special]['Salary']) if dk else 1.5*metadata[special]['Salary'])+sum(metadata[p]['Salary'] for p in flex)
        if salary>(50000 if dk else 60000) or len({metadata[p]['Team'] for p in (special,*flex)})!=2:
            raise ValueError('Support salary/team legality failure')
    standings=_standings(standings_path)
    if standings.EntryId.isna().any() or standings.EntryId.duplicated().any():raise ValueError('Nonunique entry IDs')
    if 'TimeRemaining' in standings and not pd.to_numeric(standings.TimeRemaining).eq(0).all():raise ValueError('Unfinished standings')
    scores=official_scores(standings);points=published_player_scores(standings,dk)
    mine=standings.EntryName.fillna('').str.match('(?i)^'+re.escape(username)+r'(?:\s|$)').to_numpy()
    active=Counter();background=Counter();unparsed=0
    for raw,score,is_mine in zip(standings.Lineup,scores,mine):
        if is_mine:continue
        try:key=parse_roster(raw)
        except ValueError:unparsed+=1;continue
        if int(round(100*(1.5*points[key[0]]+sum(points[p] for p in key[1]))))!=score:
            raise ValueError('Special-role points do not reconcile')
        target=background if excluded.intersection((key[0],*key[1])) else active
        target[key]+=1
    n=sum(active.values());background_n=sum(background.values());own_n=int(mine.sum())
    if n+background_n+unparsed+own_n!=len(standings):raise ValueError('Full-field strata do not reconcile')
    if not n:raise ValueError('No conditional playable opponents')
    ownership=Counter()
    for (special,flex),count in active.items():
        for player in (special,*flex):ownership[player]+=count
    chalk=[player for player,_ in ownership.most_common(15)]
    names=sorted(set(metadata)|set(ownership)|{p for key in candidate_keys+field_keys for p in (key[0],*key[1])})
    mapping={name:i for i,name in enumerate(names)}
    pairs=[tuple(sorted((mapping[a],mapping[b]))) for a,b in combinations(chalk,2)]
    def picks(keys):return np.array([[mapping[key[0]],*[mapping[p] for p in key[1]]] for key in keys],dtype=int)
    actual_features=single_game_features(picks(list(active)),len(names),pairs)
    y=np.asarray(actual_features@(np.array(list(active.values()))/n)).ravel()
    duplicate=observed_duplicate_curve(np.array(list(active.values()),dtype=np.int64),n)
    tolerance=.005
    # Necessary support-size bound under the same expected entry-band tolerance.
    lower_bound=sum(max(0,float(f)-tolerance)*n/(n if high is None else high)
        for f,(_,high) in zip(duplicate,DUPLICATE_BANDS))
    per_roster_singleton_mass=(1/n)*(1-1/n)**(n-1) if n>1 else 1.
    minimum_singleton_support=max(0,float(duplicate[0])-tolerance)/per_roster_singleton_mass
    report=dict(schema=1,development_only=True,untouched_validation=False,contest_id=manifest['contest_id'],
        format=manifest['format'],package_sha256=file_hash(package),standings_sha256=file_hash(standings_path),
        full_contest_entries=len(standings),user_entries=own_n,unparsed_or_empty_opponents=unparsed,
        retained_inactive_roster_opponents=background_n,retained_inactive_distinct_rosters=len(background),
        conditional_opponents=n,conditional_scope='Rosters containing neither excluded player; other player statuses not independently audited',conditional_distinct_rosters=len(active),conditional_maximum_copies=max(active.values()),
        excluded_players=list(excluded_players),full_field_accounting_reconciled=True,
        feature_tolerance_probability=tolerance,duplicate_tolerance_probability=tolerance,
        duplicate_bands=[list(band) for band in DUPLICATE_BANDS],target_duplicate_curve=duplicate.tolist(),
        minimum_expected_unique_at_band_tolerance=lower_bound,pair_count=len(pairs),
        iid_singleton_required_support_lower_bound=minimum_singleton_support,
        iid_singleton_necessary_integer_support=math.ceil(minimum_singleton_support),
        iid_singleton_bound_basis='Each p*(1-p)^(N-1) is at most (1/N)*(1-1/N)^(N-1); sum over support',
        results={},live_model_changed=False,payouts_evaluated=False,
        limitation='Conditional fit only; retained background is historical observed data, not a forecast of future inactive entries')
    atomic_report(output,report)
    for label,keys in [('candidate_pool',candidate_keys),('frozen_opponent_support',field_keys)]:
        counts=Counter(keys);support=list(counts)
        features=single_game_features(picks(support),len(names),pairs)
        prior=np.array(list(counts.values()),float);prior/=prior.sum()
        begin=time.monotonic()
        result=dict(support_size=len(support),band_bound_certifies_insufficient_support=lower_bound>len(support),
            maximum_expected_singleton_fraction=min(1.,len(support)*per_roster_singleton_mass),
            singleton_bound_certifies_insufficient_support=minimum_singleton_support>len(support),
            max_iterations=max_iterations,prior='captured row frequencies normalized over unique support')
        print('Starting '+label+': '+str(len(support))+' support rosters at N='+str(n),flush=True)
        try:
            fit=fit_joint_field(features,y,prior,n,duplicate,feature_tolerance=tolerance,
                duplicate_tolerance=tolerance,max_iterations=max_iterations,seed=83)
            result.update(status='accepted',diagnostics=fit.diagnostics,sampled_entries=int(fit.counts.sum()))
        except JointFitNotConverged as exc:
            result.update(status='rejected_nonconvergence',diagnostics=exc.diagnostics)
        except ValueError as exc:
            result.update(status='rejected_input_or_support',reason=str(exc))
        result['seconds']=time.monotonic()-begin
        report['results'][label]=result;report['seconds']=time.monotonic()-started
        atomic_report(output,report)
        print(json.dumps({'support':label,'status':result['status'],'seconds':result['seconds'],
            'max_feature_error':result.get('diagnostics',{}).get('max_feature_error'),
            'max_duplicate_band_error':result.get('diagnostics',{}).get('max_duplicate_band_error')}),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',required=True);parser.add_argument('--standings',required=True)
    parser.add_argument('--username',default='meitzlah78')
    parser.add_argument('--exclude-player',action='append',default=[])
    parser.add_argument('--max-iterations',type=int,default=500);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    run(args.package,args.standings,args.username,args.exclude_player,args.output,args.max_iterations)

if __name__=='__main__':main()
