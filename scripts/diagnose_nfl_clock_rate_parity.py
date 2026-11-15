"""Matched subset restoration of archived input rates, not event-lever ablation."""
import hashlib,json
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from simmah_nfl_clock_rebuild_offline import simulate


def run(prior):
    prior=Path(prior);out=prior/'clock-policy-audit';out.mkdir(exist_ok=True)
    b=json.loads((prior/'clock-rebuild/baseline_comparison.json').read_text())
    with ZipFile(prior/'Simmah_2024_Postfix_Clock_Replay.zip') as z:arch=json.loads(z.read('fullgame-outcome-clock-2024.json'))
    clock=json.loads((prior/'outcome-clock-2022-2023.json').read_text())
    t=json.loads((prior.parent/'situational-results/tuning.json').read_text());decision=t['models'][str(t['chosen']['league']['decision'])]
    base=b['parameters'];outcomes={**base,**{k:v for k,v in arch['learned_parameters'].items() if k in base}}
    rates={'penalty_rate':arch['clock_rates']['no_play_penalty'],'oob_run':arch['clock_rates']['oob_run'],'oob_pass':arch['clock_rates']['oob_pass']}
    arms={'outcome_rates_restored':outcomes,'clock_rates_restored':{**base,**rates},'both_rate_sets_restored':{**outcomes,**rates}}
    games=[json.loads(p.read_text())['game_id'] for p in sorted((prior/'clock-rebuild/baseline-games').glob('*.json'))[:10]]
    results={}
    for arm,parameters in arms.items():
        batches=[]
        for game in games:
            for seed in [17311,29107]:
                key=int(hashlib.sha256(f'{game}|{seed}'.encode()).hexdigest()[:16],16)
                batches.append(simulate(512,key,clock,decision,parameters))
        results[arm]={c:{k:float(np.mean([b[c][k] for b in batches])) for k in batches[0][c]} for c in ['means','audit','clock_events','clock_seconds']}
        print(arm,json.dumps(results[arm]['means']),flush=True)
    result={'scope':'First ten sorted games; original matched seeds and 512 draws; fixed policies and random stream layout',
        'purpose':'Restore exact archived parameter values to isolate reconstruction errors. Does not test learned fourth-down or explosive-run candidates.',
        'games':games,'arms':results,'limitations':'Penalty field/down handling, management, scoring mechanisms, original RNG and historical player allocation still differ; not exact baseline recovery.',
        '2025':'not opened','production':'unchanged','four_arm_event_lever_ablations':'not run'}
    (out/'rate_restoration.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':
    import sys
    run(sys.argv[1])
