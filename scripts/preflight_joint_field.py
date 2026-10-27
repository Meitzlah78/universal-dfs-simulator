"""Read-only development audit of saved NFL single-game support and standings."""
import argparse
from collections import Counter
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import linprog
from simmah_joint_field import DUPLICATE_BANDS, single_game_features
from simmah_slate_replay import canonical, parse_roster, _standings, official_scores, published_player_scores
from simmah_contest_history import name_key


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def audit(package,standings_path,username,*,top_players=15,tolerance=.005):
    if type(top_players) is not int or top_players<2 or not np.isfinite(tolerance) or not 0<tolerance<1:
        raise ValueError('Positive player count and probability tolerance required')
    with zipfile.ZipFile(package) as z:
        manifest=json.loads(z.read('manifest.json'))
        def member(name):
            raw=z.read(name);expected=manifest['files'][name]
            if len(raw)!=expected['bytes'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']:
                raise ValueError('Package member integrity failed: '+name)
            return raw
        import io
        pool=pd.read_csv(io.BytesIO(member('player_pool.csv')))
        candidates=pd.read_csv(io.BytesIO(member('candidates.csv')))
        field=pd.read_csv(io.BytesIO(member('opponent_field.csv')))
        state=dict(json.loads(member('solver/runtime_state.json'))['value'])
    dk=manifest['format']=='DraftKings Showdown'
    if not dk and manifest['format']!='FanDuel Single Game':raise ValueError('NFL single-game packages required')
    slots=['Captain','Flex1','Flex2','Flex3','Flex4','Flex5'] if dk else ['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5']
    candidate_keys=[canonical(row) for row in candidates[slots].itertuples(index=False,name=None)]
    field_keys=[canonical(row) for row in field[slots].itertuples(index=False,name=None)]
    metadata={name_key(row['Name']):row for row in pool.to_dict('records')}
    salary_key='dk_build_salary_range_draftkings_showdown' if dk else 'fd_build_salary_range_single_game'
    salary_min=state[salary_key]['value'][0]
    def legal(key):
        special,flex=key
        if any(p not in metadata for p in (special,*flex)):return False
        special_salary=metadata[special].get('CaptainSalary',1.5*metadata[special]['Salary']) if dk else 1.5*metadata[special]['Salary']
        salary=special_salary+sum(metadata[p]['Salary'] for p in flex)
        return salary_min<=salary<=(50000 if dk else 60000) and len({metadata[p]['Team'] for p in (special,*flex)})==2
    if not all(legal(key) for key in candidate_keys):raise ValueError('Candidate salary/team legality failed')
    standings=_standings(standings_path)
    if standings.EntryId.isna().any() or standings.EntryId.duplicated().any():raise ValueError('Nonunique entry IDs')
    if 'TimeRemaining' in standings and not pd.to_numeric(standings.TimeRemaining).eq(0).all():raise ValueError('Unfinished standings')
    scores=official_scores(standings)
    score_map=published_player_scores(standings,dk)
    display_names={name_key(p):str(p) for p in standings.Player.dropna()}
    display_names.update({key:str(row['Name']) for key,row in metadata.items()})
    mine=standings.EntryName.fillna('').str.match('(?i)^'+re.escape(username)+r'(?:\s|$)').to_numpy()
    counts=Counter();unparsed=0;own=0
    for raw,points,is_mine in zip(standings.Lineup,scores,mine):
        if is_mine:own+=1;continue
        try:key=parse_roster(raw)
        except ValueError:unparsed+=1;continue
        special,flex=key
        actual=int(round(100*(1.5*score_map[special]+sum(score_map[p] for p in flex))))
        if actual!=points:raise ValueError('Special-role score reconciliation failed')
        counts[key]+=1
    n=sum(counts.values())
    if not n:raise ValueError('No complete scored opponents')
    ownership=Counter()
    for key,count in counts.items():
        for player in (key[0],*key[1]):ownership[player]+=count
    chalk=[p for p,_ in ownership.most_common(top_players)]
    names=sorted(set(metadata)|set(ownership)|{p for key in candidate_keys+field_keys for p in (key[0],*key[1])})
    index={name:i for i,name in enumerate(names)}
    pair_names=list(combinations(chalk,2))
    pairs=[tuple(sorted((index[a],index[b]))) for a,b in pair_names]
    def picks(keys):return np.asarray([[index[key[0]],*[index[p] for p in key[1]]] for key in keys],dtype=int)
    actual_keys=list(counts)
    actual_features=single_game_features(picks(actual_keys),len(names),pairs)
    target=np.asarray(actual_features@(np.array(list(counts.values()))/n)).ravel()
    bins=[];exact_min=0;relaxed_min=0
    for low,high in DUPLICATE_BANDS:
        matches=[count for count in counts.values() if low<=count<=(n if high is None else high)]
        entries=sum(matches);upper=n if high is None else high
        exact_min+=int(np.ceil(entries/upper));relaxed_min+=max(0,entries-tolerance*n)/upper
        bins.append(dict(band=str(low) if high==low else f'{low}–{high or "+"}',
                         unique_lineups=len(matches),entries=entries,entry_fraction=entries/n))
    reports={}
    for label,keys in [('candidate_pool',candidate_keys),('frozen_opponent_support',field_keys)]:
        unique=list(dict.fromkeys(keys));unique_set=set(unique)
        x=single_game_features(picks(unique),len(names),pairs)
        pair_counts=np.asarray(x[2*len(names):].sum(axis=1)).ravel()
        pair_target=target[2*len(names):]
        unsupported=[dict(players=list(pair_names[i]),actual_fraction=float(pair_target[i]))
                     for i in range(len(pairs)) if pair_target[i]>tolerance and pair_counts[i]==0]
        # Necessary linear feasibility only; duplicate bands are nonlinear and are not tested by this LP.
        solved=linprog(np.zeros(len(unique)),A_ub=sparse.vstack([x,-x]),
            b_ub=np.r_[target+tolerance,-target+tolerance],
            A_eq=sparse.csr_matrix(np.ones((1,len(unique)))),b_eq=[1.],bounds=(0,None),
            method='highs',options={'time_limit':20})
        status='feasible' if solved.status==0 else 'infeasible' if solved.status==2 else 'unknown'
        roles=x[:2*len(names)]
        role_solved=linprog(np.zeros(len(unique)),A_ub=sparse.vstack([roles,-roles]),
            b_ub=np.r_[target[:2*len(names)]+tolerance,-target[:2*len(names)]+tolerance],
            A_eq=sparse.csr_matrix(np.ones((1,len(unique)))),b_eq=[1.],bounds=(0,None),
            method='highs',options={'time_limit':20})
        role_status='feasible' if role_solved.status==0 else 'infeasible' if role_solved.status==2 else 'unknown'
        lower=x.min(axis=1).toarray().ravel();upper=x.max(axis=1).toarray().ravel()
        unsupported_roles=[dict(player=display_names.get(names[i%len(names)],names[i%len(names)]),role='special' if i<len(names) else 'flex',
            actual_fraction=float(target[i]),support_min=float(lower[i]),support_max=float(upper[i]))
            for i in range(2*len(names)) if target[i]<lower[i]-tolerance or target[i]>upper[i]+tolerance]
        reports[label]=dict(rows=len(keys),unique_lineups=len(unique),all_support_salary_team_legal=all(legal(k) for k in unique),
            observed_chalk_pairs=len(pairs),pairs_present=int(np.count_nonzero(pair_counts)),
            unsupported_positive_pairs=unsupported,minimum_pair_support_rows=int(pair_counts.min()),
            role_only_linear_feasibility=role_status,unsupported_role_targets=unsupported_roles,
            role_and_pair_linear_feasibility=status,linear_solver_message=solved.message,
            tolerance_probability=tolerance,
            exact_empirical_distinct_count_representable=len(unique)>=len(counts),
            band_unique_lower_bound_exceeds_support=relaxed_min>len(unique),
            actual_lineup_entry_coverage=sum(count for key,count in counts.items() if key in unique_set)/n)
    unknown_salary_entries=0;below_minimum=0;above_cap=0
    for (special,flex),count in counts.items():
        if any(p not in metadata for p in (special,*flex)):
            unknown_salary_entries+=count;continue
        special_salary=metadata[special].get('CaptainSalary',1.5*metadata[special]['Salary']) if dk else 1.5*metadata[special]['Salary']
        salary=special_salary+sum(metadata[p]['Salary'] for p in flex)
        if salary<salary_min:below_minimum+=count
        if salary>(50000 if dk else 60000):above_cap+=count
    return dict(schema=1,development_only=True,contest_id=manifest['contest_id'],format=manifest['format'],
        package_sha256=sha(package),standings_sha256=sha(standings_path),
        total_entries=len(standings),excluded_user_entries=own,unparsed_or_empty_opponents=unparsed,
        captured_build_minimum_salary=float(salary_min),actual_below_captured_build_minimum_entries=below_minimum,
        actual_above_site_cap_entries=above_cap,actual_unknown_salary_entries=unknown_salary_entries,
        complete_scored_opponents=n,distinct_opponent_lineups=len(counts),maximum_lineup_copies=max(counts.values()),
        occupied_duplicate_bands=sum(row['entries']>0 for row in bins),duplicate_bands=bins,
        duplicate_band_exact_minimum_unique_lineups=exact_min,
        duplicate_band_minimum_expected_unique_at_tolerance=relaxed_min,
        pair_selection=f'top {top_players} actual overall ownership players; retrospective development only',
        support=reports,fd_payouts_still_provisional=not dk,
        limitations=['Previously inspected slate, not untouched validation.',
          'Excluded incomplete opponents are reported separately; preserve them in subsequent payout ranks.',
          'Pair presence and linear feasibility do not establish nonlinear joint-fit convergence.',
          'FD finality is not machine-verified: no TimeRemaining column.'] if not dk else [
          'Previously inspected slate, not untouched validation.',
          'Excluded incomplete opponents are reported separately; preserve them in subsequent payout ranks.',
          'Pair presence and linear feasibility do not establish nonlinear joint-fit convergence.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',required=True);p.add_argument('--standings',required=True)
    p.add_argument('--username',default='meitzlah78');p.add_argument('--output',required=True)
    args=p.parse_args();report=audit(args.package,args.standings,args.username)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
