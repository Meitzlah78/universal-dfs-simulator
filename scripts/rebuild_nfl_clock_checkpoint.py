"""Rebuild baseline only. Does not authorize or run event-lever ablations."""
import argparse,hashlib,json
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pandas as pd
from simmah_nfl_clock_rebuild_offline import simulate,VERSION
from simmah_nfl_event_levers_offline import read_season,fit_rushing_body,evaluate_gains


def run(data,prior,out,draws):
    root=Path(data);prior=Path(prior);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    frames=[];sources=[]
    for season in [2022,2023]:
        frame,source=read_season(root,season);frames.append(frame);sources.append(source)
    train=pd.concat(frames,ignore_index=True);test,source=read_season(root,2024);sources.append(source)
    models=json.loads((prior/'event-levers/gain_models.json').read_text())
    calibrated=fit_rushing_body(models['run'],train)
    (out/'rushing_body_model.json').write_text(json.dumps(calibrated))
    diagnostic=evaluate_gains({'run':calibrated,'completion':models['completion']},test,draws=64)
    (out/'rushing_body_2024.json').write_text(json.dumps(diagnostic,indent=2))
    # Additional outcome flags are training-only; game evaluation states are generated.
    cols=['season','qtr','play_type','qb_kneel','qb_spike','sack','interception','complete_pass','yards_gained','fumble_lost','out_of_bounds','extra_point_attempt','extra_point_result','penalty']
    extra=pd.concat([pd.read_csv(root/f'play_by_play_{s}.csv.gz',usecols=cols,low_memory=False) for s in [2022,2023]],ignore_index=True)
    if set(extra.season.unique())!={2022,2023}:raise ValueError('Unexpected outcome training season')
    normal=extra.loc[extra.qtr.between(1,4)&extra.play_type.isin(['pass','run'])&extra.qb_kneel.eq(0)&extra.qb_spike.eq(0)]
    passes=normal.loc[normal.play_type.eq('pass')];throws=passes.loc[passes.sack.eq(0)&passes.interception.eq(0)]
    ball=normal.loc[normal.play_type.eq('run')|normal.complete_pass.eq(1)|normal.sack.eq(1)]
    parameters=dict(sack_rate=float(passes.sack.mean()),interception_rate=float(passes.loc[passes.sack.eq(0),'interception'].mean()),
        completion_rate=float(throws.complete_pass.mean()),fumble_loss_rate=float(ball.fumble_lost.mean()),oob_rate=float(ball.out_of_bounds.mean()),
        extra_point_rate=float(extra.loc[extra.qtr.between(1,4)&extra.extra_point_attempt.eq(1),'extra_point_result'].eq('good').mean()),
        penalty_rate=.07,receiving_yards=10.913338511221028,rushing_yards=4.494838753204696)
    # Penalty approximation is frozen, not tuned to recovered target.
    clock=json.loads((prior/'outcome-clock-2022-2023.json').read_text())
    tuning_path=prior.parent/'situational-results/tuning.json'
    tuning=json.loads(tuning_path.read_text());decision=tuning['models'][str(tuning['chosen']['league']['decision'])]
    rows=[];checkpoint=out/'baseline-games';checkpoint.mkdir(exist_ok=True)
    for game in sorted(test.game_id.unique()):
        results=[]
        for seed in [17311,29107]:
            key=int(hashlib.sha256(f'{game}|{seed}'.encode()).hexdigest()[:16],16)
            result=simulate(draws,key,clock,decision,parameters);results.append(result)
        row={'game_id':game,'batches':results};rows.append(row)
        (checkpoint/f'{game}.json').write_text(json.dumps(row))
        if len(rows)%25==0:print(f'Baseline reconstruction: {len(rows)}/285 games',flush=True)
    means={k:float(np.mean([b['means'][k] for row in rows for b in row['batches']])) for k in rows[0]['batches'][0]['means']}
    ledger={k:float(np.mean([b['clock_seconds'][k] for row in rows for b in row['batches']])) for k in rows[0]['batches'][0]['clock_seconds']}
    with ZipFile(prior/'Simmah_2024_Postfix_Clock_Replay.zip') as z:old=json.loads(z.read('fullgame-outcome-clock-2024.json'))
    reference={k:old['summary']['league'][v]['mean'] for k,v in [('snaps','snaps'),('drives','drives'),('points','total')]}
    report={'version':VERSION,'games':len(rows),'draws_per_seed':draws,'seeds':[17311,29107],
        'means':means,'clock_seconds':ledger,'max_ledger_error':max(b['ledger_max_error'] for row in rows for b in row['batches']),
        'recovered_baseline':reference,'delta_vs_recovered':{k:means[k]-v for k,v in reference.items()},
        'gate':'FAIL: original source and RNG/state implementation not recovered; new driver is not exact baseline reproduction',
        'ablations':'NOT RUN: baseline-equivalence prerequisite not met','production':'unchanged','2025':'not opened','promotion_gates':'draft',
        'limitations':['League-level event driver without original player usage allocation','Approximate penalties and timeout policy','No separate scramble process, defensive return TDs or two-point conversions','Fixed own-25 kickoff, zero kickoff clock unchanged','No certified market/weather/player calibration'],
        'parameters':parameters,'sources':sources,'rushing_body_fit':calibrated['body_calibration'],
        'source_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['simmah_nfl_clock_rebuild_offline.py','simmah_nfl_event_levers_offline.py','scripts/rebuild_nfl_clock_checkpoint.py']}}
    (out/'baseline_comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('data');p.add_argument('prior');p.add_argument('out');p.add_argument('--draws',type=int,default=512);a=p.parse_args();run(a.data,a.prior,a.out,a.draws)
