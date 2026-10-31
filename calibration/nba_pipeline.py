#!/usr/bin/env python3
"""Historical NBA exact-canonical field calibration, with explicit budgets."""
import argparse
from collections import Counter
import csv
from decimal import Decimal
from itertools import combinations
import io
import json
from pathlib import Path
import re
import shutil
from time import perf_counter
import zipfile
import numpy as np
from scipy.special import logsumexp

import single_game_pipeline as common
from nba_canonical_dp import CanonicalGraph, StateBudgetExceeded, exact_basis, legal_roster, rules

TOKEN=re.compile(r'\b(G/F|F/C|UTIL\d*|PG|SG|SF|PF|GF|FC|C|G|F)\s+')


def read_contest(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            members=[n for n in z.namelist() if n.lower().endswith('.csv') and not n.startswith('__MACOSX/')]
            if len(members)!=1:raise ValueError('One NBA standings CSV required')
            name=members[0];data=z.read(name)
    else:name=path.name;data=path.read_bytes()
    return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'),newline=''))),name


def ingest(upload, contest):
    rows=list(csv.reader(io.StringIO(upload.read_bytes().decode('utf-8-sig'),newline='')))
    dk=any('Name + ID' in r and 'Roster Position' in r for r in rows)
    platform='DraftKings' if dk else 'FanDuel'
    identity='ID' if dk else 'Id';name_key='Name' if dk else 'Nickname'
    start=next((i for i,r in enumerate(rows) if identity in r and name_key in r and 'Salary' in r),None)
    if start is None:raise ValueError('Original NBA salary/player table required')
    header=rows[start];cols={k:header.index(k) for k in [identity,name_key,'Position','Salary',*(['TeamAbbrev','Game Info'] if dk else ['Team','Opponent','Game'])]}
    slot_names=None
    if not dk:
        if len(rows[0])>=13 and rows[0][0]=='entry_id':slot_names=tuple(rows[0][4:13])
        elif tuple(rows[0][:9]) in (('PG','PG','SG','SG','SF','SF','PF','PF','C'),('PG','SG','SF','PF','C','G/F','F/C','UTIL','UTIL')):slot_names=tuple(rows[0][:9])
    rule=rules(platform,slot_names)
    players=[];ids=set();names={}
    normalize=lambda value:' '.join(value.split())
    for row in rows[start+1:]:
        if len(row)<=max(cols.values()) or not row[cols[identity]].strip():continue
        pid=row[cols[identity]].strip();name=normalize(row[cols[name_key]])
        positions=tuple(row[cols['Position']].split('/'));salary=Decimal(row[cols['Salary']])
        if pid in ids or name in names:raise ValueError('Ambiguous NBA player ID or name')
        if not set(positions)<=set(('PG','SG','SF','PF','C')) or salary<=0 or salary!=int(salary):raise ValueError('Invalid NBA salary or eligibility')
        team=row[cols['TeamAbbrev' if dk else 'Team']].strip()
        if dk:
            game=re.match(r'(\w+)@(\w+)\s+',row[cols['Game Info']])
            if not game or team not in game.group(1,2):raise ValueError('NBA salary game/team mismatch')
            game='@'.join(sorted(game.group(1,2)))
        else:
            opponent=row[cols['Opponent']].strip()
            if not opponent or team==opponent:raise ValueError('Invalid NBA opponent')
            game='@'.join(sorted((team,opponent)))
        p=dict(id=pid,name=name,positions=positions,salary=int(salary),team=team,game=game)
        players.append(p);ids.add(pid);names[name]=pid
    if not players:raise ValueError('Empty NBA salary table')
    contest_rows,member=read_contest(contest)
    match=re.fullmatch(r'contest-standings-(\d+)\.csv',member) if dk else re.fullmatch(r'(\d+-\d+)\.csv',member)
    if not match:raise ValueError('Contest filename must preserve its platform ID')
    contest_id=match[1]
    cc=2 if dk else 1
    source_ids={r[cc] for r in rows[1:] if len(r)>cc and r[0].isdigit() and re.fullmatch(r'\d+(?:-\d+)?',r[cc])}
    if source_ids and contest_id not in source_ids:raise ValueError('NBA entries and standings contest IDs conflict')
    byid={p['id']:p for p in players};scores={}
    for row in contest_rows:
        if not row.get('Player'):continue
        if dk:
            pid=names.get(normalize(row['Player']))
        else:
            m=re.search(r'\(([^()]+)\)$',row['Player']);pid=m[1] if m else None
        if pid not in byid:raise ValueError('Unmapped NBA published player score')
        score=Decimal(row['FPTS'])
        if pid in scores and scores[pid]!=score:raise ValueError('Conflicting NBA player scores')
        scores[pid]=score
    observed=Counter();seen=set();missing=0;maximum=Decimal(0)
    expected_slots=Counter(rule['slots'])
    for row in contest_rows:
        eid=row.get('EntryId',row.get('Entry ID','')).strip()
        if not eid:continue
        if eid in seen:raise ValueError('Duplicate NBA entry IDs')
        seen.add(eid)
        if row.get('TimeRemaining','0').strip()!='0':raise ValueError('NBA standings are not final')
        text=row.get('Lineup','').strip()
        if not text:missing+=1;continue
        parts=TOKEN.split(text);roles=parts[1::2];labels=[normalize(s.strip(' ,')) for s in parts[2::2]]
        if dk:
            if Counter(roles)!=expected_slots or any(n not in names for n in labels):raise ValueError('NBA standings slots/names do not map to this salary table')
            picked=[names[n] for n in labels]
            # Validate the actual uploaded slot assignment as well as the
            # canonical roster's existence of a legal assignment.
            for slot,pid in zip(roles,picked):
                i=rule['slots'].index(slot)
                if not set(byid[pid]['positions'])&rule['eligibility'][i]:raise ValueError('NBA source slot eligibility mismatch')
        else:
            picked=re.findall(r'\(([^()]+)\)(?=,|$)',text)
        if any(pid not in byid for pid in picked) or not legal_roster([byid[pid] for pid in picked],rule):raise ValueError('Illegal NBA roster under configured salary, position, team or game rules')
        if any(pid not in scores for pid in picked):raise ValueError('Missing NBA published score')
        error=abs(sum((scores[pid] for pid in picked),Decimal(0))-Decimal(row['Points']))
        maximum=max(maximum,error)
        if error>Decimal('.011'):raise ValueError('NBA roster score does not reconcile')
        observed[tuple(sorted(picked))]+=1
    n=sum(observed.values())
    if not n:raise ValueError('No complete NBA rosters')
    counts=Counter()
    for roster,copies in observed.items():
        for pid in roster:counts[pid]+=copies
    for p in players:p['historical_count']=counts[p['id']]
    # Later dependent columns preferentially omit high-volume nodes, avoiding
    # the rare-anchor gauge that slowed earlier single-game experiments.
    players.sort(key=lambda p:(p['historical_count'],p['id']))
    scope=dict(recorded_entries=len(seen),complete_rosters=n,missing_rosters=missing,unique_rosters=len(observed))
    checks=dict(platform=platform,format='NBA Classic',contest_id=contest_id,players=len(players),
                maximum_score_error=str(maximum),salary_cap=rule['salary_cap'],
                rule_provenance='Original salary-table eligibility and entry slots plus explicitly configured Simmah site salary/team/game limits',
                pairing_evidence='Exact embedded contest ID' if source_ids else 'Contest ID from standings; standalone salaries require dispatcher-reviewed pairing',**scope)
    return players,observed,scope,contest_id,rule,checks


class NBAOracle:
    def __init__(self, graph, players, coordinate,T,offset,entries):
        self.graph=graph;self.nodes=graph.nodes;self.T=T;self.offset=offset;self.count=graph.count;self.entries=entries
        self.keep=np.arange(len(coordinate));self.coordinate=coordinate
        self.original_counts=np.array([entries,*[p['historical_count'] for p in players]],dtype=np.int64)
        byid={p['id']:p['historical_count'] for p in players}
        self.counts=np.array([byid[pid] for pid,j in sorted(coordinate.items(),key=lambda kv:kv[1])],dtype=np.int64)
        self.b=self.counts/entries;self.original_target=self.original_counts/entries
    def evaluate(self,theta):
        z,mean=self.graph.evaluate(theta);original=self.offset+self.T@mean
        return dict(value=z-np.log(self.count)-float(theta@self.b),gradient=mean-self.b,mean=mean,raw_log_partition=z,
                    normalization_error=self.graph.last_normalization_error,original_expectations=original,original_residual=original-self.original_target)
    def partition(self,theta):return self.graph.evaluate(theta,False)


def mini_validate(graph, players, observed, rule, coordinate, forced, out):
    byid={p['id']:p for p in players};base=set(next(iter(observed)))
    for p in players:
        if p['historical_count'] and len(base)<len(rule['slots'])+5:base.add(p['id'])
    subset=[byid[pid] for pid in sorted(base)]
    mini=CanonicalGraph(subset,rule,coordinate,forced=forced,max_states=250000,max_seconds=30)
    matrix=[]
    for chosen in combinations(subset,len(rule['slots'])):
        if not set(forced)<={p['id'] for p in chosen} or not legal_roster(chosen,rule):continue
        row=np.zeros(len(coordinate),dtype=int)
        for p in chosen:
            if p['id'] in coordinate:row[coordinate[p['id']]]=1
        matrix.append(row)
    A=np.array(matrix,dtype=int)
    if len(A)!=mini.count:raise AssertionError('NBA canonical support count mismatch')
    theta=np.random.default_rng(391).normal(0,.3,len(coordinate));checks=[]
    for label,point in [('zero',np.zeros(len(coordinate))),('nonzero',theta)]:
        z,mean=mini.evaluate(point);reference=logsumexp(A@point);refmean=A.T@np.exp(A@point-reference)
        check=dict(case=label,partition_error=abs(z-reference),expectation_error=float(abs(mean-refmean).max()))
        if max(check['partition_error'],check['expectation_error'])>1e-10:raise AssertionError('NBA mini moments mismatch')
        checks.append(check)
    d=np.random.default_rng(82).normal(size=len(theta));d/=np.linalg.norm(d);z,mean=mini.evaluate(theta)
    sweep=[dict(step=h,error=abs((mini.evaluate(theta+h*d,False)-mini.evaluate(theta-h*d,False))/(2*h)-mean@d)) for h in (1e-3,1e-4,1e-5,1e-6)]
    common.save(out/'mini_validation.json',dict(canonical_rosters=len(A),checks=checks,directional_sweep=sweep))
    return mini,A,theta


def run(upload,contest,out,max_states=4000000,max_seconds=90):
    started=perf_counter();out.mkdir(parents=True)
    source={key:dict(filename=p.name,sha256=common.digest(p)) for key,p in [('upload',upload),('contest',contest)]}
    players,observed,scope,cid,rule,checks=ingest(upload,contest);common.save(out/'ingestion_checks.json',checks)
    common.emit('nba_ingestion_passed',**checks)
    active=[p for p in players if p['historical_count']>0];forced=[p['id'] for p in players if p['historical_count']==scope['complete_rosters']]
    graph=CanonicalGraph(active,rule,max_states=max_states,max_seconds=max_seconds,forced=forced)
    if graph.count>np.iinfo(np.int64).max:raise StateBudgetExceeded('Exact count exceeds current binary128 graph-file integer format')
    coordinate,T,offset,rank=exact_basis(graph,observed,players)
    graph.remap(coordinate);common.save(out/'graph_stats.json',graph.stats);common.save(out/'rank_verification.json',rank)
    common.emit('nba_graph_and_rank_verified',**graph.stats,**rank)
    oracle=NBAOracle(graph,players,coordinate,T,offset,scope['complete_rosters'])
    if not len(coordinate):raise ValueError('Deterministic NBA face has no optimization coordinates; separate deterministic verification required')
    mini,A,minitheta=mini_validate(graph,players,observed,rule,coordinate,forced,out)
    uniform=oracle.evaluate(np.zeros(len(coordinate)))
    if abs(uniform['raw_log_partition']-np.log(graph.count))>1e-10:raise AssertionError('NBA zero-potential partition/count mismatch')
    scale=1/np.sqrt(oracle.b*(1-oracle.b));theta,fit,warm=common.fit64(oracle,out,scale)
    theta,fit,quad=common.refine_quad(oracle,theta,scale,out,mini,A,minitheta)
    fresh=oracle.evaluate(theta);final=common.metrics(fresh)
    status='verified_convergence' if common.passed(final) and quad['status']=='verified_convergence' else 'stopped_without_verified_convergence'
    collision=float(np.exp(oracle.partition(2*theta)-2*fresh['raw_log_partition']))
    observed_pairs=sum(v*(v-1)//2 for v in observed.values());n=scope['complete_rosters'];expected=n*(n-1)/2*collision
    concentration=dict(observed_equal_roster_pairs=observed_pairs,fitted_expected_equal_roster_pairs=expected,
                       fitted_pair_collision_probability=collision,observed_to_fitted_pair_ratio=observed_pairs/expected)
    result=dict(status=status,platform=checks['platform'],format='NBA Classic',scope=scope,source=source,
        active_support_count=graph.count,optimizer_dimension=len(coordinate),original_rows=len(players)+1,
        final_float64=final,quad=quad,rank=rank,float64_run=warm,roster_concentration=concentration,
        elapsed_seconds=perf_counter()-started,rule_provenance=checks['rule_provenance'])
    common.save(out/'results.json',result)
    common.save(out/'constraint_verification.json',[dict(player_id=p['id'],name=p['name'],target_count=p['historical_count'],denominator=n,fitted_probability=float(fresh['original_expectations'][i+1]),residual=float(fresh['original_residual'][i+1])) for i,p in enumerate(players)])
    common.save(out/'feature_manifest.json',dict(players=players,coordinate=coordinate,T=T.tolist(),offset=offset.tolist(),forced_players=forced,rules={k:[sorted(x) for x in v] if k=='eligibility' else v for k,v in rule.items()},source=source))
    for key,p in [('upload',upload),('contest',contest)]:
        assert common.digest(p)==source[key]['sha256']
    (out/'structural_report.md').write_text(f'# NBA historical calibration\n\nStatus: **{status}**. Contest {cid}.\n\n{n:,} complete entries, {scope["unique_rosters"]:,} unique observed rosters, {graph.count:,} exact canonical rosters on the historical active face. Flexible-position assignments are counted once per physical player set. Original salary/player IDs and scores were verified.\n\nFresh rounded-float64 ownership residual: {final["original_residual_max"]:.12g}. The original constraints here are normalization and all player inclusion marginals; NFL QB-stack features are not reused. Exact rational reconstruction relations were checked globally by integer DP extrema. The prior is uniform over legal historical support after removing zero-ownership players and forcing ownership-one players.\n\nExpected identical pairs: {expected:,.6f}; observed: {observed_pairs:,}; observed/model ratio: {observed_pairs/expected:.6g}. This is retrospective moment calibration, not evidence of predictive ownership, duplicate realism or ROI. Team/game/salary limits are explicit configured rules as described in ingestion_checks.json.\n')
    src=out/'sources';src.mkdir();shutil.copy2(upload,src/upload.name);shutil.copy2(contest,src/contest.name)
    for name in ['nba_pipeline.py','nba_canonical_dp.py','single_game_pipeline.py','single_game_log_graph.py','single_game_quad.c','single_game_quad_support.h']:shutil.copy2(Path(__file__).parent/name,out/name)
    with zipfile.ZipFile(out.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file() and p.suffix not in ('.bin','.pyc') and p.name!='quad_optimizer':z.write(p,p.relative_to(out))
    common.emit('nba_finished',status=status,seconds=result['elapsed_seconds'],final=final,concentration=concentration)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--upload',type=Path,required=True);p.add_argument('--contest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-states',type=int,default=4000000);p.add_argument('--max-build-seconds',type=float,default=90)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Choose a fresh output directory')
    try:run(a.upload.resolve(),a.contest.resolve(),a.output.resolve(),a.max_states,a.max_build_seconds)
    except StateBudgetExceeded as error:
        common.save(a.output/'budget_status.json',dict(status='stopped_without_verified_convergence',reason=str(error)))
        raise
