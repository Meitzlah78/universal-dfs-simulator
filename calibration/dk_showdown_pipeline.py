#!/usr/bin/env python3
"""Offline DK Showdown ingestion and calibration, preserving distinct CPT/FLEX IDs.

The common six-player log-DP uses MVP as its internal captain role name. This
adapter joins DK role IDs through verified (name, team, position) records and
uses the FLEX ID as a canonical physical-player key. No FanDuel inputs are used.
"""
import argparse,csv,io,json,re,shutil,zipfile
from pathlib import Path
from collections import Counter
from decimal import Decimal
from time import perf_counter
import resource
import numpy as np
import single_game_pipeline as common
ROOT=Path(__file__).resolve().parent

def contest_rows(path):
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as z:
            members=[n for n in z.namelist() if n.lower().endswith('.csv') and not n.startswith('__MACOSX/')]
            if len(members)!=1:raise ValueError('Exactly one standings CSV required inside archive')
            member=members[0]
            with z.open(member) as raw:rows=list(csv.DictReader(io.TextIOWrapper(raw,encoding='utf-8-sig')))
        return rows,member
    with path.open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    return rows,path.name

def ingest_dk(upload,contest,cap,team_a):
    with upload.open(newline='',encoding='utf-8-sig') as f:table=list(csv.reader(f))
    candidates=[(i,r.index('Position')) for i,r in enumerate(table) if all(x in r for x in ['Name + ID','ID','Roster Position','Salary','Game Info','TeamAbbrev'])]
    if len(candidates)!=1:raise ValueError('Exactly one DK salary/player table required')
    hi,start=candidates[0];header=table[hi];fields=['Position','Name + ID','Name','ID','Roster Position','Salary','Game Info','TeamAbbrev'];cols={k:header.index(k,start) for k in fields}
    roleids={};groups={};names={};errors=[]
    norm=lambda s:' '.join(s.split())
    for line,row in enumerate(table[hi+1:],hi+2):
        if len(row)<=cols['ID'] or not row[cols['ID']]:continue
        try:
            name=norm(row[cols['Name']]);role=row[cols['Roster Position']];pid=row[cols['ID']].strip();position=row[cols['Position']].strip();team=row[cols['TeamAbbrev']].strip();game=row[cols['Game Info']].strip();salary=int(row[cols['Salary']])
            if role not in {'CPT','FLEX'} or position not in {'QB','RB','WR','TE','K','DST','D','DEF'} or salary<=0:raise ValueError('Invalid role, position or salary')
            if pid in roleids:raise ValueError('Duplicate platform role ID')
            key=(name,team,position);entry=dict(name=name,team=team,position=position,game=game,role=role,id=pid,salary=salary)
            if role in groups.setdefault(key,{}):raise ValueError('Duplicate player/role identity')
            roleids[pid]=entry;groups[key][role]=entry
        except (ValueError,IndexError) as e:errors.append(f'Player-table line {line}: {e}')
    teams=sorted({key[1] for key in groups});games={r['game'] for r in roleids.values()}
    if len(teams)!=2 or team_a not in teams or len(games)!=1:errors.append('Expected one two-team slate and valid team-a')
    players=[];external={}
    for key,roles in groups.items():
        if set(roles)!={'CPT','FLEX'}:errors.append(f'Missing CPT/FLEX pair for {key}');continue
        c,f=roles['CPT'],roles['FLEX'];pid=f['id'];name=key[0]
        if 2*c['salary']!=3*f['salary']:errors.append(f'CPT salary multiplier mismatch: {name}')
        if name in names:errors.append(f'Ambiguous standings name: {name}')
        names[name]=pid
        opponent=next((t for t in teams if t!=key[1]),None)
        p=dict(platform_player_id=pid,platform_flex_id=pid,platform_cpt_id=c['id'],name=name,position=key[2],team=key[1],opponent=opponent,game=f['game'],salary_flex=f['salary'],salary_mvp=c['salary'])
        players.append(p);external[(name,'CPT')]=pid;external[(name,'FLEX')]=pid
    contest_ids={r[2] for r in table[1:] if len(r)>3 and r[0].isdigit() and r[2].isdigit()}
    if len(contest_ids)>1:errors.append('Ambiguous contest IDs in uploaded entries file')
    rows,member=contest_rows(contest)
    member_match=re.fullmatch(r'contest-standings-(\d+)\.csv',member)
    slate=next(iter(contest_ids)) if len(contest_ids)==1 else (member_match[1] if member_match else '')
    if not slate or member!=f'contest-standings-{slate}.csv':errors.append('Standings member and uploaded contest ID do not match')
    contest_id_evidence='Matched embedded upload contest ID' if contest_ids else 'Contest ID from standings member; salary-only table has no contest ID'
    scores={};source_positions={}
    for row in rows:
        if not row.get('Player'):continue
        name=norm(row['Player']);role=row['Roster Position'].strip()
        if (name,role) not in external:errors.append(f'Unmapped scoring record {name}/{role}');continue
        key=(external[(name,role)],role);value=Decimal(row['FPTS'])
        if key in scores and scores[key]!=value:errors.append(f'Conflicting role score {name}/{role}')
        scores[key]=value;source_positions[key]=role
    byid={p['platform_player_id']:p for p in players};seen=set();observed=Counter();capt=Counter();flex=Counter();missing=0;malformed=0;score_mismatch=0;salary_violations=0;team_violations=0;maxerror=Decimal(0);salaryrange=[]
    for line,row in enumerate(rows,2):
        eid=row.get('EntryId','')
        if not eid:continue
        if eid in seen:errors.append(f'Duplicate entry ID at line {line}')
        seen.add(eid)
        text=row.get('Lineup','').strip()
        if not text:missing+=1;continue
        chunks=re.split(r'\b(CPT|FLEX)\s+',text);roles=chunks[1::2];labels=[norm(v) for v in chunks[2::2]]
        if roles!=['CPT',*['FLEX']*5] or len(set(labels))!=6 or any((n,r) not in external for n,r in zip(labels,roles)):
            malformed+=1;errors.append(f'Malformed/unmapped roster at line {line}');continue
        ids=tuple(external[(n,r)] for n,r in zip(labels,roles));roster=(ids[0],*sorted(ids[1:]));observed[roster]+=1;capt[ids[0]]+=1;flex.update(ids[1:])
        cost=byid[ids[0]]['salary_mvp']+sum(byid[pid]['salary_flex'] for pid in ids[1:]);salaryrange.append(cost)
        if cost>cap:salary_violations+=1
        if len({byid[pid]['team'] for pid in ids})!=2:team_violations+=1
        if any((pid,r) not in scores for pid,r in zip(ids,roles)):errors.append(f'Missing role score at line {line}');continue
        predicted=sum((scores[(pid,r)] for pid,r in zip(ids,roles)),Decimal(0));delta=abs(predicted-Decimal(row['Points']));maxerror=max(maxerror,delta)
        if delta>Decimal('.011'):score_mismatch+=1
    if salary_violations or team_violations or score_mismatch:errors.append(f'Illegal/score failures: salary={salary_violations}; both-teams={team_violations}; score={score_mismatch}')
    # DK scoring table supplies multiplied CPT FPTS; verify against FLEX where both exist.
    multipliers=[abs(scores[(pid,'CPT')]-Decimal('1.5')*scores[(pid,'FLEX')]) for pid in byid if (pid,'CPT') in scores and (pid,'FLEX') in scores]
    if multipliers and max(multipliers)>Decimal('.011'):errors.append('CPT/FLEX score multiplier mismatch')
    n=sum(observed.values())
    if n==0 or sum(capt.values())!=n or sum(flex.values())!=5*n:errors.append('Role count conservation failed')
    for p in players:p.update(historical_mvp_count=capt[p['platform_player_id']],historical_flex_count=flex[p['platform_player_id']])
    if errors:raise ValueError(json.dumps(errors[:30],indent=2))
    scope=dict(recorded_entries=len(seen),complete_rosters=n,missing_rosters=missing,unique_rosters=len(observed))
    verification=dict(contest_id_evidence=contest_id_evidence,platform='DraftKings',format='Showdown',game=next(iter(games)),players=len(players),role_records=len(roleids),captain_identity='Separate CPT and FLEX IDs joined by exact name/team/position; canonical physical-player key is FLEX ID',malformed_rosters=malformed,unmapped_players=0,score_check_max_error=str(maxerror),cpt_vs_flex_score_multiplier_max_error=str(max(multipliers,default=Decimal(0))),salary_violations=salary_violations,both_teams_violations=team_violations,observed_salary_range=[min(salaryrange),max(salaryrange)],configured_salary_cap=cap,salary_cap_provenance='Explicit runner parameter; roster salaries taken directly from supplied DK player table',observed_equal_roster_pairs=sum(v*(v-1)//2 for v in observed.values()),largest_roster_count=max(observed.values()),**scope)
    return sorted(players,key=lambda p:p['platform_player_id']),observed,scope,slate,verification

def run(upload,contest,out,cap,team_a):
    started=perf_counter();out.mkdir(parents=True);source={name:dict(path=str(p),filename=p.name,sha256=common.digest(p)) for name,p in [('upload',upload),('contest',contest)]}
    players,observed,scope,slate,checks=ingest_dk(upload,contest,cap,team_a);common.save(out/'dk_ingestion_checks.json',checks)
    common.emit('dk_ingestion_passed',**checks)
    m,keep,T,offset=common.manifest_for(players,observed,scope,slate,cap,team_a,source)
    m.update(platform='DraftKings',format='Showdown',internal_role_aliases={'MVP':'CPT','FLEX':'FLEX'},dk_ingestion=checks)
    m['rules'].update(captain_points_multiplier=1.5,captain_salary_multiplier=1.5,external_captain_role='CPT')
    common.save(out/'feature_manifest.json',m);common.save(out/'observed_rosters.json',[dict(canonical_cpt=r[0],flex=list(r[1:]),count=c) for r,c in observed.items()])
    counts=common.count_support(players,cap);fullcounts=common.count_support(players,cap,False);common.save(out/'support_counts.json',dict(active=counts,unrestricted=fullcounts));common.emit('dk_support_counted',active=counts['total'],unrestricted=fullcounts['total'],optimizer_coordinates=len(keep))
    mini,miniA,minitheta,minicheck=common.mini_validate(m,keep,cap,out);oracle=common.Oracle(m,keep,T,offset,counts['total'],cap)
    uniform=oracle.evaluate(np.zeros(len(keep)));error=abs(uniform['raw_log_partition']-np.log(counts['total']));assert error<1e-10
    common.save(out/'uniform_baseline.json',dict(log_partition=uniform['raw_log_partition'],integer_count_log_error=error,construction_seconds=oracle.construction_seconds,graphs=len(oracle.graphs),expectations=uniform['mean'].tolist()))
    if np.any((oracle.b<=0)|(oracle.b>=1)):raise ValueError('Target boundary requires explicit face reduction')
    scale=1/np.sqrt(oracle.b*(1-oracle.b));theta,fit,r64=common.fit64(oracle,out,scale)
    theta,fit,quad=common.refine_quad(oracle,theta,scale,out,mini,miniA,minitheta)
    fresh=oracle.evaluate(theta);final=common.metrics(fresh);verified=common.passed(final) and quad['status']=='verified_convergence'
    collision=float(np.exp(oracle.partition(2*theta)-2*fresh['raw_log_partition']));N=scope['complete_rosters'];pairs=N*(N-1)//2;observed_pairs=checks['observed_equal_roster_pairs']
    realism=dict(observed_equal_roster_pairs=observed_pairs,fitted_expected_equal_roster_pairs=pairs*collision,fitted_pair_collision_probability=collision,observed_to_fitted_pair_ratio=observed_pairs/(pairs*collision))
    common.save(out/'roster_concentration.json',realism)
    verification=[dict(key=row['key'],target_count=row['historical_target_count'],denominator=N,fitted_probability=float(value),residual=float(value-row['historical_target_count']/N)) for row,value in zip(m['all_original_rows'],fresh['original_expectations'])]
    common.save(out/'constraint_verification.json',verification)
    for key,p in [('upload',upload),('contest',contest)]:assert common.digest(p)==source[key]['sha256']
    summary=dict(status='verified_convergence' if verified else 'stopped_without_verified_convergence',platform='DraftKings',format='Showdown',slate_id=slate,source=source,scope=scope,players=len(players),original_rows=len(m['all_original_rows']),retained_rows=len(m['retained_rows']),optimizer_dimension=len(keep),anchors=m['anchors'],active_support_count=counts['total'],unrestricted_support_count=fullcounts['total'],final_float64=final,quad=quad,float64_run=r64,elapsed_seconds=perf_counter()-started,peak_rss_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,roster_concentration=realism)
    common.save(out/'results.json',summary);common.report(out,summary,m)
    report=out/'structural_report.md';text=report.read_text().replace('MVP','CPT').replace('with no NE–CHI checkpoint inputs','without any previous fitted checkpoint inputs');text+='\nDK role mapping: the shared solver uses the internal role name MVP as an alias for CPT. The original DK CPT and FLEX IDs are both retained in the manifest; the FLEX ID is the canonical physical-player key. Source role-specific salaries are used directly. The DK standings provide already-multiplied CPT FPTS; roster scores are checked against those values. No FanDuel player IDs, salaries, scores or fitted targets are used.\n';report.write_text(text)
    src=out/'sources';src.mkdir();shutil.copy2(upload,src/upload.name);shutil.copy2(contest,src/contest.name)
    for name in ['dk_showdown_pipeline.py','single_game_pipeline.py','single_game_log_graph.py','single_game_quad.c','single_game_quad_support.h']:shutil.copy2(ROOT/name,out/name)
    (out/'README.md').write_text('# Offline DK Showdown historical calibration\n\nSee structural_report.md and dk_ingestion_checks.json. Reproduce from the extracted directory with a new output folder:\n\n```bash\nOPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 dk_showdown_pipeline.py --upload "sources/'+upload.name+'" --contest "sources/'+contest.name+'" --team-a '+team_a+' --salary-cap '+str(cap)+' --output replay\n```\n\nRequires Python, NumPy, SciPy, GCC and libquadmath. Native graph files/executable are regenerated. The common six-player solver uses MVP internally as the CPT alias; external platform role IDs and prices remain distinct in the manifest. This fit uses historical observed targets and ownership-zero masks and is not an out-of-sample prediction test. No Git/production/remote changes are performed.\n')
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file() and p.suffix not in {'.bin','.pyc'} and p.name!='quad_optimizer':z.write(p,p.relative_to(out))
    common.emit('dk_finished',status=summary['status'],seconds=summary['elapsed_seconds'],final=final,observed_to_fitted_pair_ratio=realism['observed_to_fitted_pair_ratio'],archive=str(archive))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--upload',type=Path,required=True);p.add_argument('--contest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--team-a',required=True);p.add_argument('--salary-cap',type=int,default=50000);a=p.parse_args()
    if a.output.exists():raise ValueError('Use a new output directory to preserve prior fits')
    run(a.upload.resolve(),a.contest.resolve(),a.output.resolve(),a.salary_cap,a.team_a)
if __name__=='__main__':main()
