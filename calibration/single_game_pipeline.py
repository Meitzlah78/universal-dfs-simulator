#!/usr/bin/env python3
"""Offline six-player, two-team FanDuel historical KL calibration.

One invocation validates CSVs, generates a manifest, checks a miniature exact
support, counts full legal support, fits moments, optionally refines in GCC
binary128, independently verifies, and writes a report. No Git or live APIs.
"""
import argparse
from collections import Counter
import csv
from decimal import Decimal, localcontext
import hashlib
from itertools import combinations
import json
from math import gcd
from pathlib import Path
import re
import resource
import shutil
import subprocess
from time import perf_counter
import zipfile

import numpy as np
from scipy.optimize import fmin_l_bfgs_b
from scipy.special import logsumexp
from single_game_log_graph import LogDPEvaluator

ROOT=Path(__file__).resolve().parent

def emit(stage,**kw):print(json.dumps(dict(stage=stage,**kw),allow_nan=False),flush=True)
def save(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class SlateValidationError(ValueError):
    pass


def ingest(upload,contest,cap,team_a):
    errors=[]
    with upload.open(encoding='utf-8-sig',newline='') as f:table=list(csv.reader(f))
    headers=[(i,r.index('Id')) for i,r in enumerate(table) if 'Id' in r and 'MVP 1.5x Salary' in r]
    if len(headers)!=1:raise SlateValidationError('Expected exactly one uploaded player table')
    hi,_=headers[0];header=table[hi];cols={k:header.index(k) for k in ['Id','Position','Nickname','Salary','MVP 1.5x Salary','Game','Team','Opponent']}
    players=[];byid={}
    for line,row in enumerate(table[hi+1:],hi+2):
        if len(row)<=cols['Id'] or not row[cols['Id']]:continue
        try:
            p=dict(platform_player_id=row[cols['Id']],name=row[cols['Nickname']],position=row[cols['Position']],
                   team=row[cols['Team']],opponent=row[cols['Opponent']],game=row[cols['Game']],
                   salary_flex=int(row[cols['Salary']]),salary_mvp=int(row[cols['MVP 1.5x Salary']]))
            if p['platform_player_id'] in byid:errors.append(f'Duplicate player ID at row {line}')
            if not p['platform_player_id'] or p['position'] not in {'QB','RB','WR','TE','K','D','DEF','DST'} or not p['team'] or not p['opponent']:errors.append(f'Invalid metadata at row {line}')
            if min(p['salary_flex'],p['salary_mvp'])<=0:errors.append(f'Nonpositive salary at row {line}')
            players.append(p);byid[p['platform_player_id']]=p
        except (ValueError,IndexError) as exc:errors.append(f'Player row {line}: {exc}')
    teams=sorted({p['team'] for p in players})
    if len(teams)!=2 or team_a not in teams:errors.append('Exactly two teams and valid --team-a required')
    for p in players:
        if p['opponent'] not in teams or p['opponent']==p['team']:errors.append(f'Invalid opponent: {p["platform_player_id"]}')
    contest_column=table[0].index('contest_id') if 'contest_id' in table[0] else None
    slate_ids={r[contest_column] for r in table[1:] if contest_column is not None and len(r)>contest_column and re.fullmatch(r'\d+-\d+',r[contest_column])}
    # Standalone FD salary tables lack a contest ID. The archive dispatcher
    # requires an explicitly reviewed pairing before invoking this fallback;
    # ID/salary/score legality is still checked below on every observed roster.
    if not slate_ids and contest_column is None and re.fullmatch(r'\d+-\d+',contest.stem):slate_ids={contest.stem}
    if len(slate_ids)!=1:errors.append('Ambiguous contest ID in upload')
    elif contest.stem not in slate_ids:errors.append('Contest filename does not match upload contest ID')
    with contest.open(encoding='utf-8-sig',newline='') as f:records=list(csv.DictReader(f))
    observed=Counter();mvp=Counter();flex=Counter();missing=0;ids=set();scores={};valid_records=[]
    for row in records:
        if row.get('Player'):
            match=re.search(r'\(([^()]+)\)$',row['Player'])
            if not match or match[1] not in byid:errors.append('Unresolved scoring-table player ID');continue
            pid=match[1]
            if row['Roster Position']!=byid[pid]['position']:errors.append(f'Scoring position mismatch: {pid}')
            if int(row['Salary'])!=byid[pid]['salary_flex']:errors.append(f'Scoring salary mismatch: {pid}')
            scores[pid]=Decimal(row['FPTS'])
        if not row.get('EntryId'):continue
        eid=row['EntryId']
        if eid in ids:errors.append(f'Duplicate entry ID: {eid}')
        ids.add(eid)
        if not row.get('Lineup'):missing+=1;continue
        roster=tuple(re.findall(r'\(([^()]+)\)(?=,|$)',row['Lineup']))
        if len(roster)!=6 or len(set(roster))!=6 or any(pid not in byid for pid in roster):errors.append(f'Malformed roster: {eid}');continue
        labels=[part.strip().split(' ',1)[0] for part in row['Lineup'].split(',')]
        if labels!=[byid[pid]['position'] for pid in roster]:errors.append(f'Lineup position mismatch: {eid}')
        salary=byid[roster[0]]['salary_mvp']+sum(byid[pid]['salary_flex'] for pid in roster[1:])
        if salary>cap or len({byid[pid]['team'] for pid in roster})!=2:errors.append(f'Illegal roster: {eid}')
        key=(roster[0],*sorted(roster[1:]));observed[key]+=1;mvp[key[0]]+=1;flex.update(key[1:]);valid_records.append((key,Decimal(row['Points']),eid))
    for roster,points,eid in valid_records:
        if any(pid not in scores for pid in roster):errors.append(f'Missing FPTS metadata: {eid}');continue
        predicted=Decimal('1.5')*scores[roster[0]]+sum((scores[pid] for pid in roster[1:]),Decimal(0))
        if abs(predicted-points)>Decimal('.011'):errors.append(f'First-slot-MVP score mismatch: {eid}')
    n=sum(observed.values())
    if n==0 or sum(mvp.values())!=n or sum(flex.values())!=5*n:errors.append('Historical role-count mass mismatch')
    if errors:raise SlateValidationError(json.dumps(errors,indent=2))
    players.sort(key=lambda p:p['platform_player_id'])
    for p in players:p.update(historical_mvp_count=mvp[p['platform_player_id']],historical_flex_count=flex[p['platform_player_id']])
    return players,observed,dict(complete_rosters=n,missing_rosters=missing,unique_rosters=len(observed),recorded_entries=len(ids)),next(iter(slate_ids))


def features(roster,manifest):
    """Direct original indicator evaluation, independent of graph transitions."""
    byid={p['platform_player_id']:p for p in manifest['players']}
    counts=Counter(roster);a=manifest['team_a'];ne=sum(byid[pid]['team']==a for pid in roster)
    out=[]
    for r in manifest['all_original_rows']:
        kind=r['kind']
        if kind=='anchor':v=1
        elif kind=='role':v=int(roster[0]==r['player_id']) if r['role']=='MVP' else int(r['player_id'] in roster[1:])
        elif kind=='team_count':v=int(ne==r['roster_player_count'])
        else:
            q=r['qb_id'];same=sum(byid[pid]['team']==byid[q]['team'] and byid[pid]['position'] in {'WR','TE'} for pid in roster[1:])
            v=int(roster[0]==q and same==r['same_team_wrte_flex_count'])
        out.append(v)
    return np.array(out,dtype=np.int64)


def manifest_for(players,observed,scope,slate,cap,team_a,source):
    teams=sorted({p['team'] for p in players});team_b=next(t for t in teams if t!=team_a)
    def top(pool,role):return max(pool,key=lambda p:(p['historical_'+role.lower()+'_count'],p['platform_player_id']))['platform_player_id']
    qbs=[top([p for p in players if p['team']==team and p['position']=='QB'],'MVP') for team in [team_a,team_b]]
    anchors=dict(MVP=top(players,'MVP'),FLEX_A=top([p for p in players if p['team']==team_a],'FLEX'),FLEX_B=top([p for p in players if p['team']==team_b],'FLEX'))
    rows=[dict(key='normalization',kind='anchor')]
    for role in ['MVP','FLEX']:
        rows += [dict(key=f'{role}:{p["platform_player_id"]}',kind='role',role=role,player_id=p['platform_player_id'],team=p['team']) for p in players]
    for qb in qbs:
        rows += [dict(key=f'stack:{qb}:{b}',kind='joint_qb_stack',qb_id=qb,same_team_wrte_flex_count=b) for b in range(5)]
    rows += [dict(key=f'team:{team_a}:{b}',kind='team_count',team=team_a,roster_player_count=b) for b in range(1,6)]
    for j,row in enumerate(rows):row['original_row_index']=j
    m=dict(slate_id=slate,team_a=team_a,team_b=team_b,players=players,scope=scope,source=source,
           rules=dict(salary_cap=cap,roster_size=6,flex_slots=5,both_teams_required=True,salary_cap_provenance='Explicit runner configuration; not independently supplied in these CSVs'),
           qb_ids=qbs,anchors=anchors,all_original_rows=rows)
    sums=np.zeros(len(rows),dtype=np.int64)
    vectors=[]
    for roster,count in observed.items():
        f=features(roster,m);sums+=count*f;vectors.append(f)
    for row,count in zip(rows,sums):row['historical_target_count']=int(count)
    omit={f'MVP:{anchors["MVP"]}',f'FLEX:{anchors["FLEX_A"]}',f'FLEX:{anchors["FLEX_B"]}',f'stack:{qbs[0]}:4',f'stack:{qbs[1]}:4',f'team:{team_a}:5'}
    retained=[dict(r,row_index=i) for i,r in enumerate(r for r in rows if r['key'] not in omit)]
    bykey={r['key']:r for r in retained};equations={}
    equations[f'MVP:{anchors["MVP"]}']={'normalization':1,**{r['key']:-1 for r in rows if r['kind']=='role' and r['role']=='MVP' and r['key'] not in omit}}
    equations[f'team:{team_a}:5']={'normalization':1,**{f'team:{team_a}:{b}':-1 for b in range(1,5)}}
    for qb in qbs:equations[f'stack:{qb}:4']={f'MVP:{qb}':1,**{f'stack:{qb}:{b}':-1 for b in range(4)}}
    equations[f'FLEX:{anchors["FLEX_A"]}']={**{f'team:{team_a}:{b}':b for b in range(1,6)},**{r['key']:-1 for r in rows if r['kind']=='role' and r['team']==team_a and r['key']!=f'FLEX:{anchors["FLEX_A"]}'}}
    equations[f'FLEX:{anchors["FLEX_B"]}']={'normalization':5,**{r['key']:-1 for r in rows if r['kind']=='role' and r['role']=='FLEX' and r['key']!=f'FLEX:{anchors["FLEX_B"]}'}}
    def expand(key):
        if key in bykey:return {str(bykey[key]['row_index']):1}
        ans=Counter()
        for other,c in equations[key].items():
            for idx,d in expand(other).items():ans[idx]+=c*d
        return {i:int(c) for i,c in ans.items() if c}
    omitted=[dict(r,symbolic_coefficients=equations[r['key']],reduced_index_coefficients=expand(r['key'])) for r in rows if r['key'] in omit]
    zero=[r['row_index'] for r in retained if r['kind']=='role' and r['historical_target_count']==0]
    m.update(retained_rows=retained,reduction=dict(omitted_rows=omitted),verification=dict(retained_zero_role_indices=zero))
    keep=np.setdiff1d(np.arange(len(retained)),[0,*zero]);kmap={int(k):i for i,k in enumerate(keep)}
    T=np.zeros((len(rows),len(keep)),dtype=np.int64);offset=np.zeros(len(rows),dtype=np.int64)
    reduction=np.zeros((len(rows),len(retained)),dtype=np.int64)
    for r in rows:
        j=r['original_row_index']
        for idx,c in expand(r['key']).items():
            reduction[j,int(idx)]=c
            if int(idx)==0:offset[j]+=c
            elif int(idx) in kmap:T[j,kmap[int(idx)]]+=c
    full=np.vstack(vectors);retix=[r['original_row_index'] for r in retained]
    reconstructed=full[:,retix]@reduction.T
    assert np.array_equal(full,reconstructed),'Observed reconstruction identity failure'
    assert np.array_equal(reduction@np.array([r['historical_target_count'] for r in retained]),sums)
    rank=int(np.linalg.matrix_rank(full[:,np.array(retix)[keep]]-full[:,np.array(retix)[keep]].mean(axis=0)))
    m['verification'].update(observed_integer_identity_max_residual=0,observed_centered_numerical_rank=rank,optimizer_dimension=len(keep),original_rows=len(rows),retained_rows=len(retained))
    return m,keep,T,offset


def count_support(players,cap,active=True):
    unit=0
    for p in players:
        for key in ['salary_flex','salary_mvp']:unit=gcd(unit,p[key])
    unit=gcd(unit,cap)
    def subsets(pool,budget):
        if budget<0 or len(pool)<5:return 0
        dp=np.zeros((6,budget//unit+1),dtype=np.int64);dp[0,0]=1
        for p in pool:
            s=p['salary_flex']//unit
            if s>budget//unit:continue
            for k in range(5,0,-1):dp[k,s:]+=dp[k-1,:-s]
        return int(dp[5].sum())
    per=[]
    for mvp in players:
        if active and mvp['historical_mvp_count']==0:continue
        pool=[p for p in players if p is not mvp and (not active or p['historical_flex_count']>0)]
        budget=cap-mvp['salary_mvp']
        count=subsets(pool,budget)-subsets([p for p in pool if p['team']==mvp['team']],budget)
        per.append(dict(mvp_id=mvp['platform_player_id'],count=count))
    return dict(total=sum(r['count'] for r in per),per_mvp=per,salary_integer_unit=unit,method='Exact int64 salary-subset recurrence, subtracting same-team rosters; no structural feature state')


class Oracle:
    def __init__(self,m,keep,T,offset,support,cap):
        self.m=m;self.keep=keep;self.T=T;self.offset=offset;self.count=support
        self.entries=m['scope']['complete_rosters'];self.counts=np.array([m['retained_rows'][int(k)]['historical_target_count'] for k in keep],dtype=np.int64)
        self.b=self.counts/self.entries;self.original_counts=np.array([r['historical_target_count'] for r in m['all_original_rows']],dtype=np.int64)
        self.original_target=self.original_counts/self.entries
        started=perf_counter();ids=[p['platform_player_id'] for p in m['players']]
        self.graphs=[]
        for p in m['players']:
            if p['historical_mvp_count']:
                self.graphs.append(LogDPEvaluator(m,ids,cap,fixed_mvp_id=p['platform_player_id']))
        self.construction_seconds=perf_counter()-started
        self.nodes=[n for g in self.graphs for n in g.nodes]
    def evaluate(self,theta):
        logs=[];means=[]
        for graph in self.graphs:
            z,mean=graph.evaluate(theta);logs.append(z);means.append(mean)
        z=float(logsumexp(logs));probs=np.exp(np.array(logs)-z);mean=np.array(means).T@probs
        original=self.offset+self.T@mean
        return dict(value=z-np.log(self.count)-float(theta@self.b),gradient=mean-self.b,mean=mean,raw_log_partition=z,
                    normalization_error=float(abs(probs.sum()-1)),original_expectations=original,original_residual=original-self.original_target)
    def partition(self,theta):return float(logsumexp([g.evaluate(theta,False) for g in self.graphs]))


def metrics(r):
    return dict(raw_gradient_max=float(np.abs(r['gradient']).max()),original_residual_max=float(np.abs(r['original_residual']).max()),normalization_error=r['normalization_error'],objective=r['value'])
def passed(v):return v['raw_gradient_max']<=1e-9 and v['original_residual_max']<=1e-8 and v['normalization_error']<=1e-12 and all(np.isfinite(x) for x in v.values())


def mini_validate(m,keep,cap,out):
    # Mix designated QBs, high-frequency FLEXs, and low-salary alternatives.
    players=m['players'];byid={p['platform_player_id']:p for p in players}
    ids=set(m['qb_ids'])
    for team in [m['team_a'],m['team_b']]:
        candidates=[p for p in players if p['team']==team and p['historical_flex_count']>0]
        ids.update(p['platform_player_id'] for p in sorted(candidates,key=lambda p:-p['historical_flex_count'])[:4])
        ids.update(p['platform_player_id'] for p in sorted(candidates,key=lambda p:(p['salary_flex'],p['platform_player_id']))[:3])
    ids=sorted(ids);rows=[]
    for pid in ids:
        if not byid[pid]['historical_mvp_count']:continue
        pool=[q for q in ids if q!=pid and byid[q]['historical_flex_count']>0]
        for flex in combinations(pool,5):
            roster=(pid,*flex)
            if byid[pid]['salary_mvp']+sum(byid[q]['salary_flex'] for q in flex)>cap or len({byid[q]['team'] for q in roster})!=2:continue
            rows.append(features(roster,m))
    if not rows:raise SlateValidationError('No miniature verification support')
    full=np.vstack(rows);retix=np.array([r['original_row_index'] for r in m['retained_rows']]);A=full[:,retix[keep]]
    graph=LogDPEvaluator(m,ids,cap);rng=np.random.default_rng(391);theta=rng.normal(0,.25,len(keep));checks=[]
    for label,point in [('zero',np.zeros(len(keep))),('moderate',theta)]:
        z,mean=graph.evaluate(point);energies=A@point;refz=float(logsumexp(energies));refmean=A.T@np.exp(energies-refz)
        check=dict(case=label,log_partition_error=abs(z-refz),expectation_max_error=float(np.abs(mean-refmean).max()));assert check['log_partition_error']<1e-10 and check['expectation_max_error']<1e-10;checks.append(check)
    d=rng.normal(size=len(keep));d/=np.linalg.norm(d);z,mean=graph.evaluate(theta);directional=[]
    for h in [1e-3,1e-4,1e-5,1e-6]:
        diff=(graph.evaluate(theta+h*d,False)-graph.evaluate(theta-h*d,False))/(2*h)
        directional.append(dict(step=h,absolute_error=abs(diff-float(mean@d))))
    result=dict(players=ids,rosters=len(rows),exercised_coordinates=np.flatnonzero(A.any(axis=0)).tolist(),checks=checks,directional_sweep=directional)
    save(out/'mini_validation.json',result);emit('mini_validation_passed',rosters=len(rows),exercised_coordinates=len(result['exercised_coordinates']),checks=checks)
    return graph,A,theta,result


def serialize(path,nodes,points,target,counts,support,entries):
    def ints(f,x):f.write(np.asarray(x,dtype=np.int64).tobytes())
    with path.open('wb') as f:
        f.write(b'NDPQ0001');ints(f,[len(nodes),len(points),len(counts),support,entries]);f.write(np.asarray(points,dtype=np.float64).tobytes());f.write(np.asarray(target,dtype=np.float64).tobytes());ints(f,counts)
        for node in nodes:
            ints(f,[len(node['layers'])])
            for l in node['layers']:
                ints(f,[l['previous_size'],l['next_size'],len(l['skip_src']),len(l['add_src']),l['role_coordinate'] if l['role_coordinate'] is not None else -1])
                for key in ['skip_src','skip_dst','add_src','add_dst']:ints(f,l[key])
            ints(f,[node['final_size'],len(node['terminal_indices'])]);ints(f,node['terminal_indices'])
            tf=np.full((len(node['terminal_indices']),3),-1,dtype=np.int64)
            for j,row in enumerate(node['terminal_features']):
                ix=np.flatnonzero(row);assert len(ix)<=3;tf[j,:len(ix)]=ix
            ints(f,tf)


class GatesReached(Exception):pass
class BudgetReached(Exception):pass

def fit64(oracle,out,scale):
    started=perf_counter();calls=0;accepted=0;last_eta=None;last=None;eta=np.zeros(len(scale));accepted_eta=eta.copy()
    log=(out/'float64_events.jsonl').open('x')
    def write(event,x,r):
        row=dict(event=event,evaluation=calls,accepted_steps=accepted,elapsed_seconds=perf_counter()-started,eta=x.tolist(),raw_theta=(scale*x).tolist(),gradient=r['gradient'].tolist(),transformed_gradient=(scale*r['gradient']).tolist(),**metrics(r))
        log.write(json.dumps(row,allow_nan=False)+'\n');log.flush()
    def fun(x):
        nonlocal calls,last_eta,last
        if calls>=1800 or perf_counter()-started>420:raise BudgetReached()
        r=oracle.evaluate(scale*x);calls+=1;last_eta=x.copy();last=r;write('evaluation',x,r)
        return r['value'],scale*r['gradient']
    def cb(x):
        nonlocal accepted,accepted_eta
        accepted+=1;accepted_eta=x.copy()
        if not np.array_equal(x,last_eta):fun(x)
        write('accepted',x,last)
        np.savez(out/'float64_checkpoint.npz',raw_parameters=scale*x,eta=x,gradient=last['gradient'],scale=scale)
        if accepted%20==0 or passed(metrics(last)):emit('float64_progress',iterations=accepted,evaluations=calls,**metrics(last))
        if passed(metrics(last)):raise GatesReached()
    try:
        eta,_,info=fmin_l_bfgs_b(fun,eta,m=30,factr=0,pgtol=1e-11,maxiter=650,maxfun=1800,maxls=40,callback=cb);accepted_eta=eta.copy();reason=str(info['task'])
    except GatesReached:reason='Original-unit convergence gates reached'
    except BudgetReached:reason='Bounded evaluation/time budget reached; retaining last accepted state'
    final=oracle.evaluate(scale*accepted_eta);calls+=1;write('fresh_verification',accepted_eta,final);log.close()
    result=dict(status='verified_convergence' if passed(metrics(final)) else 'stopped_without_verified_convergence',reason=reason,iterations=accepted,evaluations=calls,elapsed_seconds=perf_counter()-started,**metrics(final))
    save(out/'float64_results.json',result);np.savez(out/'float64_checkpoint.npz',raw_parameters=scale*accepted_eta,eta=accepted_eta,gradient=final['gradient'],scale=scale)
    emit('float64_finished',**result)
    return scale*accepted_eta,final,result


def quad_run(exe,graph,opt,out,label,validate=False):
    cmd=[str(exe),str(graph),str(opt),str(out/f'{label}_events.jsonl'),str(out/f'{label}_final.json')]
    if validate:cmd.append('validate')
    with (out/f'{label}_console.jsonl').open('x') as f:
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1);term=None
        for line in p.stdout:
            f.write(line);f.flush();v=json.loads(line)
            if v['event']=='termination':term=v
            emit(label,**{k:v for k,v in v.items() if not isinstance(v,list)})
        stderr=p.stderr.read();code=p.wait();p.stdout.close();p.stderr.close()
        if code:raise RuntimeError(f'Binary128 kernel failed ({code}): {stderr}')
    return json.loads((out/f'{label}_final.json').read_text()),term


def refine_quad(oracle,theta,scale,out,mini,miniA,mini_theta):
    k=len(theta);n=len(oracle.original_counts);h=1e-3;H=np.empty((k,k));started=perf_counter()
    for j in range(k):
        d=np.zeros(k);d[j]=h;H[:,j]=(oracle.evaluate(theta+d)['mean']-oracle.evaluate(theta-d)['mean'])/(2*h)
        if (j+1)%15==0:emit('hessian_progress',coordinates=j+1,total=k,elapsed_seconds=perf_counter()-started)
    asym=float(np.max(np.abs(H-H.T)));H=(H+H.T)/2;scaled=scale[:,None]*H*scale[None,:];eigen=np.linalg.eigvalsh(scaled)
    if eigen[0]<=0:raise RuntimeError('Estimated Hessian metric not positive definite')
    metric=dict(step=h,seconds=perf_counter()-started,raw_symmetry_error=asym,scaled_eigen_min=float(eigen[0]),scaled_eigen_max=float(eigen[-1]),scaled_condition_estimate=float(eigen[-1]/eigen[0]))
    save(out/'hessian_metric.json',metric);np.savez(out/'hessian_metric.npz',raw_hessian=H,scaled_hessian=scaled,scale=scale);emit('hessian_ready',**metric)
    exe=out/'quad_optimizer';subprocess.run(['gcc','-O2','-std=gnu11',f'-DK={k}',f'-DORIGINAL={n}',str(ROOT/'single_game_quad.c'),'-o',str(exe),'-lquadmath','-lm'],check=True)
    def opt_file(path,initial):
        with path.open('wb') as f:
            f.write(b'NQOPT001')
            for x,dtype in [(initial,np.float64),(np.eye(k),np.int64),(np.eye(k),np.int64),(scale,np.float64),(scaled,np.float64),(oracle.T,np.int64),(oracle.offset,np.int64),(oracle.original_counts,np.int64)]:f.write(np.asarray(x,dtype=dtype).tobytes())
    miniopt=out/'mini_optimizer.bin';opt_file(miniopt,mini_theta);minigraph=out/'mini_graph.bin';serialize(minigraph,mini.nodes,[mini_theta],oracle.b,oracle.counts,len(miniA),oracle.entries)
    final,_=quad_run(exe,minigraph,miniopt,out,'quad_mini',True)
    with localcontext() as ctx:
        ctx.prec=80;point=[Decimal(x) for x in final['raw_theta']];indices=[np.flatnonzero(row) for row in miniA]
        weights=[sum((point[int(i)] for i in ix),Decimal(0)).exp() for ix in indices];total=sum(weights,Decimal(0));mean=[Decimal(0)]*k
        for ix,w in zip(indices,weights):
            for i in ix:mean[int(i)]+=w
        mean=[x/total for x in mean];refg=[x-Decimal(int(c))/Decimal(oracle.entries) for x,c in zip(mean,oracle.counts)]
        maxmean=max(abs(Decimal(x)-y) for x,y in zip(final['mean'],mean));maxg=max(abs(Decimal(x)-y) for x,y in zip(final['raw_gradient'],refg))
        refobjective=total.ln()-Decimal(len(miniA)).ln()-sum((t*Decimal(int(c))/Decimal(oracle.entries) for t,c in zip(point,oracle.counts)),Decimal(0))
        maxobjective=abs(refobjective-Decimal(final['objective']))
        assert maxmean<Decimal('1e-27') and maxg<Decimal('1e-27') and maxobjective<Decimal('1e-27')
        small=dict(reference_decimal_digits=80,rosters=len(miniA),mean_max_error=str(maxmean),raw_gradient_max_error=str(maxg),objective_error=str(maxobjective),passed=True)
    save(out/'quad_small_validation.json',small);emit('quad_small_validation_passed',**small)
    fullgraph=out/'full_graph.bin';serialize(fullgraph,oracle.nodes,[theta],oracle.b,oracle.counts,oracle.count,oracle.entries);opt=out/'full_optimizer.bin';opt_file(opt,theta)
    final,term=quad_run(exe,fullgraph,opt,out,'quad_full')
    rounded=np.array([float(x) for x in final['raw_theta']]);standard=oracle.evaluate(rounded)
    with localcontext() as ctx:
        ctx.prec=80
        err=max(abs(Decimal(x)-Decimal(int(c))/Decimal(oracle.entries)) for x,c in zip(final['original_expectations'],oracle.original_counts))
        raw=max(abs(Decimal(x)) for x in final['raw_gradient']);norm=abs(Decimal(final['normalization_error']))
        verified=raw<=Decimal('1e-9') and err<=Decimal('1e-8') and norm<=Decimal('1e-12')
        assert verified==(term['status']=='verified_convergence')
    result=dict(status=term['status'],termination=term,fresh_binary128=dict(raw_gradient_max=str(raw),original_residual_max=str(err),normalization_error=str(norm)),independent_rounded_float64=metrics(standard),float64_gates_passed=passed(metrics(standard)),metric=metric,small_validation=small)
    save(out/'quad_results.json',result);np.savez(out/'terminal_rounded_parameters.npz',raw_parameters=rounded,keep=oracle.keep)
    return rounded,standard,result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--upload',type=Path,required=True);parser.add_argument('--contest',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--team-a',required=True);parser.add_argument('--salary-cap',type=int,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise ValueError('Output directory already exists; choose a new directory to preserve prior runs')
    out.mkdir(parents=True);started=perf_counter();upload=args.upload.resolve();contest=args.contest.resolve()
    source={name:dict(path=str(p),filename=p.name,sha256=digest(p)) for name,p in [('upload',upload),('contest',contest)]}
    players,observed,scope,slate=ingest(upload,contest,args.salary_cap,args.team_a)
    m,keep,T,offset=manifest_for(players,observed,scope,slate,args.salary_cap,args.team_a,source);save(out/'feature_manifest.json',m)
    save(out/'observed_rosters.json',[dict(mvp=r[0],flex=list(r[1:]),count=c) for r,c in observed.items()])
    emit('source_validation_passed',slate_id=slate,players=len(players),**scope,original_rows=len(m['all_original_rows']),retained_rows=len(m['retained_rows']),zero_role_rows=len(m['verification']['retained_zero_role_indices']),optimizer_dimension=len(keep),anchors=m['anchors'])
    counts=count_support(players,args.salary_cap);fullcounts=count_support(players,args.salary_cap,False);save(out/'support_counts.json',dict(active=counts,unrestricted=fullcounts));emit('independent_support_count',active=counts['total'],unrestricted=fullcounts['total'])
    mini,miniA,minitheta,minicheck=mini_validate(m,keep,args.salary_cap,out)
    oracle=Oracle(m,keep,T,offset,counts['total'],args.salary_cap);uniform=oracle.evaluate(np.zeros(len(keep)))
    error=abs(uniform['raw_log_partition']-np.log(counts['total']));assert error<1e-10
    baseline=dict(log_partition=uniform['raw_log_partition'],integer_count_log_error=error,construction_seconds=oracle.construction_seconds,graphs=len(oracle.graphs),expectations=uniform['mean'].tolist())
    save(out/'uniform_baseline.json',baseline);emit('cached_baseline_passed',**{k:v for k,v in baseline.items() if k!='expectations'})
    b=oracle.b
    if np.any((b<=0)|(b>=1)):raise SlateValidationError('Nonconstant coordinate target lies at boundary; further face reduction required')
    scale=1/np.sqrt(b*(1-b));theta,fit,result64=fit64(oracle,out,scale)
    # Automatic archived fits always receive fresh binary128 and independent
    # rounded-float64 verification, even when the warm fit already passed.
    theta,fit,quad=refine_quad(oracle,theta,scale,out,mini,miniA,minitheta)
    fresh=oracle.evaluate(theta);finalmetrics=metrics(fresh);verified=passed(finalmetrics) and (quad is None or quad['status']=='verified_convergence')
    retix=np.array([r['original_row_index'] for r in m['retained_rows']]);logz=fresh['raw_log_partition']
    top=[]
    for roster,c in observed.most_common(10):
        f=features(roster,m)[retix[keep]];p=float(np.exp(f@theta-logz));top.append(dict(mvp=roster[0],flex=list(roster[1:]),observed_count=c,fitted_probability=p,expected_count=scope['complete_rosters']*p))
    collision=float(np.exp(oracle.partition(2*theta)-2*logz));N=scope['complete_rosters'];pairs=N*(N-1)/2
    realism=dict(observed_equal_roster_pairs=sum(c*(c-1)//2 for c in observed.values()),fitted_expected_equal_roster_pairs=pairs*collision,fitted_pair_collision_probability=collision,top_observed_rosters=top,interpretation='Historical descriptive check. Moment convergence does not imply roster-duplicate realism or prospective accuracy.')
    save(out/'roster_concentration.json',realism)
    relative=[]
    for row,p in zip(m['all_original_rows'],fresh['original_expectations']):
        target=row['historical_target_count']/N
        relative.append(dict(key=row['key'],target_count=row['historical_target_count'],target_probability=target,fitted_probability=float(p),absolute_residual=float(abs(p-target)),relative_residual=None if target==0 else float(abs(p-target)/target)))
    save(out/'constraint_verification.json',relative)
    for name,p in [('upload',upload),('contest',contest)]:assert digest(p)==source[name]['sha256']
    summary=dict(status='verified_convergence' if verified else 'stopped_without_verified_convergence',slate_id=slate,source=source,scope=scope,players=len(players),original_rows=len(m['all_original_rows']),retained_rows=len(m['retained_rows']),optimizer_dimension=len(keep),anchors=m['anchors'],active_support_count=counts['total'],unrestricted_support_count=fullcounts['total'],final_float64=finalmetrics,quad=quad,float64_run=result64,elapsed_seconds=perf_counter()-started,peak_rss_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,roster_concentration=realism)
    save(out/'results.json',summary)
    report(out,summary,m)
    # Include sources and runner, but reconstruct large native graph binaries on replay.
    src=out/'sources';src.mkdir();shutil.copy2(upload,src/upload.name);shutil.copy2(contest,src/contest.name)
    for name in ['single_game_pipeline.py','single_game_log_graph.py','single_game_quad.c','single_game_quad_support.h']:shutil.copy2(ROOT/name,out/name)
    (out/'README.md').write_text(f'# Offline historical calibration\n\nStatus: **{summary["status"]}**. See structural_report.md and results.json.\n\nReproduce from raw inputs in a NEW directory:\n\n```bash\nOPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 single_game_pipeline.py --upload sources/{upload.name} --contest sources/{contest.name} --team-a {args.team_a} --salary-cap {args.salary_cap} --output replay\n```\n\nRequires Python with NumPy/SciPy and GCC with libquadmath for refinement. No download or package installation is performed. The runner supports this six-player, two-team, no-salary-floor format. Numerical rank and strict terminal gates are reported separately. Source metadata and configurable contest rules must be checked for each slate. Native binary graph files and the compiled executable are regenerated and excluded from this archive.\n')
    archive=out.parent/(out.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file() and p.suffix not in {'.bin','.pyc'} and p.name!='quad_optimizer':z.write(p,p.relative_to(out))
    emit('finished',status=summary['status'],elapsed_seconds=summary['elapsed_seconds'],final=finalmetrics,archive=str(archive),report=str(out/'structural_report.md'))


def report(out,s,m):
    names={p['platform_player_id']:p['name'] for p in m['players']};a=s['anchors'];v=s['final_float64'];q=s['quad']
    lines=[f'# {m["team_a"]}–{m["team_b"]} historical structural calibration','',f'Status: **{s["status"]}**. Contest `{s["slate_id"]}`. This report describes a new end-to-end offline run from raw CSVs, with no NE–CHI checkpoint inputs.','',f'{s["scope"]["complete_rosters"]:,} complete entries and {s["scope"]["unique_rosters"]:,} unique rosters were parsed; {s["scope"]["missing_rosters"]:,} entries without rosters were excluded from all target denominators. The pool has {s["players"]} players. Player IDs, teams, positions and both uploaded role salaries are preserved. Every complete entry passed identity, roster size, team, configured salary cap and first-slot-MVP score checks.','',f'The configured cap is ${m["rules"]["salary_cap"]:,}; it is an explicit input, not independently documented in these CSVs. The format assumes one MVP, five FLEX, both teams and no salary floor.','',f'The original {s["original_rows"]}-row system includes normalization, all role indicators, two designated QB joint stack partitions and the team-count partition. Six exact reconstruction equations leave {s["retained_rows"]} rows. All {len(m["verification"]["retained_zero_role_indices"])} zero-count retained role rows remain in the manifest. Removing these and normalization gives {s["optimizer_dimension"]} optimizer coordinates. Observed roster reconstruction residuals are exactly zero under integer arithmetic. The observed centered numerical rank is {m["verification"]["observed_centered_numerical_rank"]}; this is not an exact algebraic rank certificate.','',f'Omitted role anchors: MVP **{names[a["MVP"]]}**, {m["team_a"]} FLEX **{names[a["FLEX_A"]]}**, {m["team_b"]} FLEX **{names[a["FLEX_B"]]}**. Each was selected reproducibly by the largest historical count within its category. This does not establish an optimal basis.','',f'An independent exact integer salary-grid recurrence counted **{s["active_support_count"]:,}** historically permitted lineups and **{s["unrestricted_support_count"]:,}** unrestricted legal lineups under the configured rules. The zero-potential log-DP partition agrees with the integer active count. Small enumerable support checks compare partition values, feature expectations and directional finite differences. The full evaluator aggregates graph states; it does not enumerate every lineup on each call.','','The prior is uniform over the historical active face. The minimized dual is log Z − log(support size) − θᵀb; at an exact fit its negative is KL divergence in nats. This prior differs from a uniform prior over the unrestricted site-legal support.','',f'The float64 fit recorded {s["float64_run"]["iterations"]} accepted iterations and {s["float64_run"]["evaluations"]} complete calls including terminal verification. Its status is `{s["float64_run"]["status"]}`. The optimizer uses fixed target-variance scaling, with no target relaxation, probability clipping, ridge penalty or dual-weight pruning.','', '| Fresh independent rounded float64 gate | Residual | Threshold |','|---|---:|---:|',f'| Raw gradient infinity norm | {v["raw_gradient_max"]:.10g} | 1e-9 |',f'| All {s["original_rows"]} reconstructed constraints | {v["original_residual_max"]:.10g} | 1e-8 |',f'| Normalization | {v["normalization_error"]:.10g} | 1e-12 |','']
    if q:
        f=q['fresh_binary128'];t=q['termination'];lines += [f'The separately logged binary128 refinement used GCC `__float128` (113-bit significand) for parameters, forward/backward accumulation, rational targets, gradients and strong-Wolfe objective differences. Its initial inverse metric came from a symmetrized central-difference Hessian estimate in float64, promoted to binary128. An independent 80-digit Decimal brute-force small-support check passed before refinement. Precision, metric and optimizer implementation change together; no isolated causal claim follows.','',f'The binary128 run recorded {t["accepted_updates"]} accepted update(s) and {t["evaluations_including_fresh"]} complete calls including a fresh terminal verification. Raw gradient: {f["raw_gradient_max"]}; reconstructed residual: {f["original_residual_max"]}; normalization: {f["normalization_error"]}. Exact decimal logs are retained.','']
    r=s['roster_concentration'];lines += [f'Total measured pipeline time: {s["elapsed_seconds"]:.3f} seconds, excluding packaging. Peak Python process RSS: {s["peak_rss_MiB"]:.2f} MiB (child-process peaks are not included). Caching stores graphs in ordinary process memory.','',f'Observed equal-roster entry pairs: **{r["observed_equal_roster_pairs"]:,}**. Under independent draws from the fitted model, expected equal-roster pairs: **{r["fitted_expected_equal_roster_pairs"]:,.2f}**. This descriptive comparison is separate from constraint convergence; the model was not fitted to duplicate counts.','', 'Passing moment gates establishes numerical agreement with the selected historical targets. It does not establish exact arithmetic identities for floating-point gradients, prospective field accuracy, duplicate realism, payout performance or ROI. This result is specific to this source pair and configured rules.','', 'Source SHA-256:','']
    for name,value in s['source'].items():lines += [f'- `{value["filename"]}`: `{value["sha256"]}`']
    lines += ['', 'Source hashes were checked again after execution. All accepted float64 states and evaluations are logged; binary128 logs retain decimal parameters, gradients and trial values. Earlier NE–CHI files remain separate. No Git, production pipeline or remote branch operations were performed, and no repository HEAD was verified.']
    (out/'structural_report.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':main()
