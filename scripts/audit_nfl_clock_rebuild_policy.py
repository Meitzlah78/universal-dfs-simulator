"""Instrumentation-only matched ten-game diagnosis; no policy changes or ablations."""
import hashlib,json
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from simmah_nfl_clock_rebuild_offline import simulate


def run(prior):
    prior=Path(prior);out=prior/'clock-policy-audit';out.mkdir(exist_ok=True)
    before=json.loads((prior/'clock-rebuild/baseline_comparison.json').read_text())
    clock=json.loads((prior/'outcome-clock-2022-2023.json').read_text())
    tuning=json.loads((prior.parent/'situational-results/tuning.json').read_text());decision=tuning['models'][str(tuning['chosen']['league']['decision'])]
    with ZipFile(prior/'Simmah_2024_Postfix_Clock_Replay.zip') as z:archive=json.loads(z.read('fullgame-outcome-clock-2024.json'))
    archived={r['game_id']:r['arms']['league'] for r in archive['results']}
    paths=sorted((prior/'clock-rebuild/baseline-games').glob('*.json'))[:10];rows=[]
    for path in paths:
        original=json.loads(path.read_text());game=original['game_id'];batches=[]
        for slot,seed in enumerate([17311,29107]):
            key=int(hashlib.sha256(f'{game}|{seed}'.encode()).hexdigest()[:16],16)
            r=simulate(before['draws_per_seed'],key,clock,decision,before['parameters'])
            for k in ['means','clock_seconds','ledger_max_error','draws']:
                if r[k]!=original['batches'][slot][k]:raise ValueError('Instrumentation changed old outputs: '+game+' '+k)
            batches.append(r)
        row={'game_id':game,'batches':batches};rows.append(row);(out/(game+'.json')).write_text(json.dumps(row))
        print('Matched audit '+str(len(rows))+'/10',flush=True)
    average=lambda category:{k:float(np.mean([b[category][k] for r in rows for b in r['batches']])) for k in rows[0]['batches'][0][category]}
    oldledger={k:float(np.mean([archived[r['game_id']]['clock_ledger'][k] for r in rows])) for k in archived[rows[0]['game_id']]['clock_ledger']}
    play={'status':'League archive lacks pass/run counters; hybrid-only tail audit cannot be substituted for league baseline'}
    means=average('means');audit=average('audit');events=average('clock_events');seconds=average('clock_seconds')
    oldmeans={k:float(np.mean([archived[r['game_id']][v]['mean'] for r in rows])) for k,v in [('snaps','snaps'),('drives','drives'),('points','total')]}
    changes={k:{'archived':v,'rebuilt':before['parameters'].get(k),'equal':before['parameters'].get(k)==v} for k,v in archive['learned_parameters'].items()}
    report={'scope':'First ten lexically sorted 2024 games; two original seeds, 512 draws each; matched diagnostic subset, not new validation',
        'games':[r['game_id'] for r in rows],'instrumentation_parity':'all previously saved means, clock seconds and ledger errors match exactly for all 20 batches',
        'rebuilt':{'means':means,'events':events,'seconds':seconds,'audit':audit},'archived':{'means':oldmeans,'ledger':oldledger,'play_audit':play,'clock_rates':archive['clock_rates']},
        'parameter_comparison':changes,
        'directly_identified_differences':[
         'Rebuild uses one pooled OOB probability for runs and completions; archive records separate oob_run and oob_pass rates',
         'Rebuild uses 0.07 no-play penalty hazard; archive records 0.06394778040173003 and defensive penalty share; rebuild consumes time but applies no penalty field/down movement',
         'Rebuild re-estimates several outcome rates with different event filters instead of reusing exact archived learned_parameters',
         'Rebuild lacks archived two-point conversions, defensive return TDs and explicit management/kneel events',
         'Rebuild timeout use is Q4 final120 only; recovered clock model also has end-Q2 profiles; original explicit timeout policy source remains unavailable',
         'Same raw seed integers do not imply same random streams: rebuilt hashes game and seed and allocates fixed 14-uniform event blocks; archive labels streams non-event-aligned, implementation unavailable'],
        'known_matching_policy':'Near-goal go when yardline_100<5; late trailing go when remaining<180; FG distance threshold yardline_100<=40; own-25 kickoff; 7-second punts/FGs. Remaining policy parity unproven.',
        'causal_attribution':'Not established: no claim any single mismatch accounts for all 4.05548 snaps; requires isolated restoration tests.',
        '2025':'not opened','production':'unchanged','four_arm_ablations':'blocked; this audit is instrumentation only'}
    (out/'comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps({'old':oldmeans,'new':means,'audit':audit,'old_clock':oldledger,'new_clock_events':events}),flush=True)

if __name__=='__main__':
    import sys
    run(sys.argv[1])
