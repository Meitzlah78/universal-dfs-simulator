"""User-authorized, slice-gated comparative research. Never production/2025."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib,json
from pathlib import Path
import numpy as np
from simmah_nfl_clock_rebuild_offline import simulate,POLICY_VERSION

ARMS=['Baseline','Fourth-Down-Only','Explosive-Run-Only','Combined']
SEEDS=[17311,29107]
CONFIG=None


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_baseline(folder):
    folder=Path(folder);report=json.loads((folder/'validation.json').read_text())
    if not (report.get('research_baseline_locked') and report.get('slice_gate') and report.get('ledger_max_error')==0):
        raise ValueError('Clock-slice research baseline is not locked; ablations blocked')
    if report['policy']!=POLICY_VERSION or report['games']!=285 or report['draws_per_game']!=1024:
        raise ValueError('Policy or 285-game/1024-draw scope mismatch')
    if not all(report['checks'][f'q{q}_{metric}']['pass'] for q in [2,4] for metric in ['snaps','defensive_timeouts']):
        raise ValueError('Required clock slice failed')
    if not report['checks'].get('q2_offensive_timeouts',{}).get('pass',False):raise ValueError('Q2 offensive timeout target failed or is missing')
    for p,digest in report['sources'].items():
        if sha(p)!=digest:raise ValueError('Baseline provenance changed: '+p)
    rows=json.loads((folder/'game_batches.json').read_text())
    if len(rows)!=285 or len({r['game_id'] for r in rows})!=285 or any(not r['game_id'].startswith('2024_') for r in rows):
        raise ValueError('Only the complete, unique 2024 set is unlocked')
    for row in rows:
        if len(row['batches'])!=2 or any(b['draws']!=512 or b['management_policy']!=POLICY_VERSION or b['ledger_max_error']!=0 for b in row['batches']):
            raise ValueError('Baseline batches do not match locked configuration')
    return report,{r['game_id']:r['batches'] for r in rows}


def init_worker(config):
    global CONFIG
    CONFIG=config


def replay_game(game):
    results={}
    for arm in ARMS[1:]:
        options={'management_policy':POLICY_VERSION}
        if arm in ['Fourth-Down-Only','Combined']:options['fourth_policy']=CONFIG['fourth']
        if arm in ['Explosive-Run-Only','Combined']:options['run_model']=CONFIG['run']
        batches=[]
        for seed in SEEDS:
            key=int(hashlib.sha256(f'{game}|{seed}'.encode()).hexdigest()[:16],16)
            r=simulate(512,key,CONFIG['clock'],CONFIG['decision'],CONFIG['parameters'],**options)
            if r['ledger_max_error']!=0:raise ValueError('Arm clock ledger failed')
            batches.append(r)
        results[arm]=batches
    return game,results


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,default=Path('late-half-v4-results'))
    parser.add_argument('--frozen',type=Path,default=Path('late-half-results/frozen_inputs.json'))
    parser.add_argument('--fourth',type=Path,default=Path('../inputs/Simmah_NFL_Event_Levers_Offline_2026-11-14/results/fourth_policy.json'))
    parser.add_argument('--run',type=Path,default=Path('../inputs/Simmah_NFL_Clock_Rebuild_2026-11-14/clock-rebuild/rushing_body_model.json'))
    parser.add_argument('--candidate-freeze',type=Path,default=Path('late-half-results/candidate_freeze.json'))
    parser.add_argument('--out',type=Path,default=Path('four-arm-v4-results'));parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();report,baseline=checked_baseline(args.baseline)
    expected=json.loads(args.candidate_freeze.read_text())
    if expected.get(str(args.fourth))!=sha(args.fourth) or expected.get(str(args.run))!=sha(args.run):
        raise ValueError('Candidate hashes differ from frozen prior trial')
    config=json.loads(args.frozen.read_text());config['fourth']=json.loads(args.fourth.read_text());config['run']=json.loads(args.run.read_text())
    for name in ['fourth','run']:
        if config[name].get('fit_seasons')!=[2022,2023]:raise ValueError('Candidate is not training-only')
    # Match the exact frozen baseline inputs rather than just their filenames.
    recorded=[p for p in report['sources'] if Path(p).name=='frozen_inputs.json']
    if len(recorded)!=1 or sha(args.frozen)!=report['sources'][recorded[0]]:raise ValueError('Baseline inputs mismatch')
    args.out.mkdir(parents=True,exist_ok=True);games=args.out/'games';games.mkdir(exist_ok=True)
    manifest={'scope':'EXPLORATORY CLOCK-SLICE-QUALIFIED RESEARCH; NOT PRODUCTION VALIDATION',
        'policy':POLICY_VERSION,'games':285,'draws_per_seed':512,'seeds':SEEDS,'arms':ARMS,
        'baseline_validation_sha256':sha(args.baseline/'validation.json'),'baseline_game_batches_sha256':sha(args.baseline/'game_batches.json'),
        'frozen_inputs_sha256':sha(args.frozen),'fourth_sha256':sha(args.fourth),'rushing_sha256':sha(args.run),
        'driver_sha256':sha('simmah_nfl_clock_rebuild_offline.py'),'runner_sha256':sha(__file__),
        'full_game_checks':report['full_game_checks'],'2025':'not opened','production':'unchanged','merge':'not authorized',
        'arm_definition_caveat':'Explosive-Run-Only switches the entire frozen empirical rushing distribution (body plus tail), not only 20+ outcomes. Combined applies that same candidate plus fourth-down policy. No refitting.',
        'random_pairing':'Game-keyed seeds and fixed-width event-index streams; not state-aligned after paths diverge',
        'evaluation_caveat':'285 game labels key league-level simulation seeds; no matchup/player calibration or independent 2024 holdout claim'}
    (args.out/'baseline_lock.json').write_text(json.dumps(manifest,indent=2))
    results={};todo=[]
    for game in sorted(baseline):
        path=games/(game+'.json')
        if path.exists():
            row=json.loads(path.read_text())
            if row.get('manifest_sha256')!=sha(args.out/'baseline_lock.json'):raise ValueError('Stale arm cache')
            results[game]=row['arms']
        else:todo.append(game)
    with ProcessPoolExecutor(max_workers=max(1,min(args.workers,8)),initializer=init_worker,initargs=(config,)) as pool:
        futures={pool.submit(replay_game,g):g for g in todo}
        for future in as_completed(futures):
            game,arms=future.result();arms['Baseline']=baseline[game];results[game]=arms
            (games/(game+'.json')).write_text(json.dumps({'game_id':game,'manifest_sha256':sha(args.out/'baseline_lock.json'),'arms':arms}))
            if len(results)%25==0:print(f'Four-arm replay {len(results)}/285',flush=True)
    means={arm:{k:float(np.mean([b['means'][k] for game in sorted(results) for b in results[game][arm]])) for k in baseline[next(iter(baseline))][0]['means']} for arm in ARMS}
    deltas={arm:{k:means[arm][k]-means['Baseline'][k] for k in means[arm]} for arm in ARMS[1:]}
    summary={'manifest':manifest,'status':'COMPLETED EXPLORATORY RESEARCH; NO PRODUCTION PROMOTION','means':means,'delta_vs_baseline':deltas,
        'late_half':{arm:{k:float(np.mean([b['late_half'][k] for game in sorted(results) for b in results[game][arm]])) for k in baseline[next(iter(baseline))][0]['late_half']} for arm in ARMS},
        'ledger_max_error':max(b['ledger_max_error'] for game in results.values() for arm in game.values() for b in arm)}
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(means),flush=True)

if __name__=='__main__':main()
