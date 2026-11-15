"""Frozen-policy diagnostic. 2024 is reused evaluation, never a fresh holdout."""
import argparse,hashlib,json
from zipfile import ZipFile
from pathlib import Path
import numpy as np
import pandas as pd
from simmah_nfl_clock_rebuild_offline import simulate,POLICY_VERSION

ROOT=Path(__file__).resolve().parents[2]
OUT=Path('late-half-results');OUT.mkdir(exist_ok=True)
# Declared before measuring 2024; exploratory tolerances, not promotion criteria.
TOLERANCES={'snaps':1.0,'defensive_timeouts':0.5}

def observed_slices(f):
    f=f.copy()
    # Timeout rows omit possession. Resolve only when the same quarter/drive
    # contains exactly one recorded offense/defense; retain ambiguous rows.
    for col in ['posteam','defteam']:
        context=f.groupby(['game_id','qtr','fixed_drive'])[col].transform(lambda v: v.dropna().iloc[0] if v.dropna().nunique()==1 else None)
        f[col]=f[col].fillna(context)
    games=sorted(f.game_id.unique());observed={} 
    snap=(f.play_type.isin(['pass','run'])|f.qb_kneel.eq(1)|f.qb_spike.eq(1))&f.extra_point_attempt.ne(1)&f.two_point_attempt.ne(1)
    for q in [2,4]:
        loc=f.qtr.eq(q)&f.quarter_seconds_remaining.between(0,120,inclusive='right')
        # Timeout team must be explicitly recorded; ambiguous drive context stays unclassified.
        for name,mask in [('snaps',snap),('defensive_timeouts',f.timeout.eq(1)&f.timeout_team.eq(f.defteam)),('offensive_timeouts',f.timeout.eq(1)&f.timeout_team.eq(f.posteam)),('all_timeouts',f.timeout.eq(1)),('unclassified_timeouts',f.timeout.eq(1)&~(f.timeout_team.eq(f.defteam)|f.timeout_team.eq(f.posteam))),('kneels',snap&f.qb_kneel.eq(1)),('spikes',snap&f.qb_spike.eq(1))]:
            counts=f.loc[loc&mask].groupby('game_id').size().reindex(games,fill_value=0)
            observed[f'q{q}_{name}']={'mean':float(counts.mean()),'per_game':counts.to_dict()}
    return f,games,snap,observed

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=ROOT/'inputs/Simmah_NFL_PBP_2022-2025_Recovered/play_by_play_2024.csv.gz')
    parser.add_argument('--frozen',type=Path,default=OUT/'frozen_inputs.json')
    parser.add_argument('--actual-audit',type=Path,default=ROOT/'inputs/Simmah_2024_Full_Game_Hybrid_Replay.zip')
    parser.add_argument('--out',type=Path,default=Path('late-half-v5-results'))
    args=parser.parse_args();data=args.data;out=args.out;out.mkdir(parents=True,exist_ok=True)
    if data.name!='play_by_play_2024.csv.gz':raise ValueError('Only 2024 evaluation is allowed')
    cols=['season','game_id','play_id','qtr','quarter_seconds_remaining','play_type','qb_kneel','qb_spike','extra_point_attempt','two_point_attempt','timeout','timeout_team','posteam','defteam','fixed_drive']
    f=pd.read_csv(data,usecols=cols,low_memory=False)
    if set(f.season.unique())!={2024} or f.duplicated(['game_id','play_id']).any():raise ValueError('Invalid evaluation data')
    f,games,snap,observed=observed_slices(f)
    frozen=json.loads(args.frozen.read_text())
    clock=frozen['clock'];decision=frozen['decision'];parameters=frozen['parameters']
    results=[]
    cached=out/'game_batches.json'
    cache_key=hashlib.sha256((hashlib.sha256(Path('simmah_nfl_clock_rebuild_offline.py').read_bytes()).hexdigest()+hashlib.sha256(args.frozen.read_bytes()).hexdigest()+POLICY_VERSION+'512|17311|29107').encode()).hexdigest()
    meta=out/'game_batches.meta.json'
    if cached.exists() and (not meta.exists() or json.loads(meta.read_text())['cache_key']!=cache_key):raise ValueError('Unverified or stale simulation cache')
    previous={r['game_id']:r for r in json.loads(cached.read_text())} if cached.exists() else {}
    meta.write_text(json.dumps({'cache_key':cache_key}))
    # Baseline mechanics unchanged except management; candidates are not applied here.
    for game in games:
        if game in previous:
            results.append(previous[game]);continue
        row={'game_id':game,'batches':[]}
        for seed in [17311,29107]:
            key=int(hashlib.sha256(f'{game}|{seed}'.encode()).hexdigest()[:16],16)
            row['batches'].append(simulate(512,key,clock,decision,parameters,management_policy=POLICY_VERSION))
        results.append(row)
        if len(results)%25==0:
            cached.write_text(json.dumps(results))
            print(f'Policy validation {len(results)}/{len(games)}',flush=True)
    batches=[b for r in results for b in r['batches']]
    simulated={k:float(np.mean([b['late_half'][k] for b in batches])) for k in batches[0]['late_half']}
    checks={}
    for q in [2,4]:
        for metric,tol in TOLERANCES.items():
            key=f'q{q}_{metric}';delta=simulated[key]-observed[key]['mean']
            checks[key]={'observed':observed[key]['mean'],'simulated':simulated[key],'delta':delta,'tolerance':tol,'pass':abs(delta)<=tol}
    # v4's explicit offensive-timeout target: same +/-0.5 event screen.
    key='q2_offensive_timeouts';delta=simulated[key]-observed[key]['mean']
    checks[key]={'observed':observed[key]['mean'],'simulated':simulated[key],'delta':delta,'tolerance':0.5,'pass':abs(delta)<=0.5}
    with ZipFile(args.actual_audit) as z:
        actual=json.loads(z.read('fullgame-actual-audit.json'))
    means={k:float(np.mean([b['means'][k] for b in batches])) for k in batches[0]['means']}
    fullgame={}
    for metric,ref in [('snaps','observed_snaps_per_game'),('drives','observed_drives_per_game'),('points','observed_total_regulation_points')]:
        target=float((snap&f.qtr.between(1,4)).sum()/len(games)) if metric=='snaps' else actual[ref]
        fullgame[metric]={'observed':target,'simulated':means[metric],'relative_error':(means[metric]-target)/target,'pass':abs(means[metric]-target)/target<=.05}
    report={'full_game_checks':fullgame,'full_game_tolerance':.05,'policy':POLICY_VERSION,'games':len(games),'draws_per_game':1024,'checks':checks,'observed':observed,'simulated':simulated,'means':{k:float(np.mean([b['means'][k] for b in batches])) for k in batches[0]['means']},'ledger_max_error':max(b['ledger_max_error'] for b in batches),'slice_gate':all(c['pass'] for c in checks.values()),'baseline_locked':False,'research_baseline_locked':False,'research_gate_scope':'User-authorized Q2/Q4 snap and defensive-timeout screens plus exact regulation accounting; not production/full-game validation','ablations':'BLOCKED pending clock-slice research gate','2025':'not opened or extracted','production':'unchanged','evaluation':'Reused 2024 diagnostics; no independent holdout claim','sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [data,args.frozen,args.actual_audit,Path('simmah_nfl_clock_rebuild_offline.py'),Path(__file__)]}}
    for q in [2,4]:
        for metric in ['offensive_timeouts','all_timeouts','kneels']:
            key=f'q{q}_{metric}'
            report.setdefault('additional_management_checks',{})[key]={'observed':observed[key]['mean'],'simulated':simulated[key],'delta':simulated[key]-observed[key]['mean']}
    report['research_baseline_locked']=report['slice_gate'] and report['ledger_max_error']==0
    if report['research_baseline_locked']:
        report['ablations']='AUTHORIZED: exploratory four-arm matrix under user-specified clock-slice gate; full-game validation remains separate'
    meta.write_text(json.dumps({'cache_key':cache_key}))
    (out/'validation.json').write_text(json.dumps(report,indent=2));(out/'game_batches.json').write_text(json.dumps(results));print(json.dumps(checks),flush=True)
if __name__=='__main__':main()
