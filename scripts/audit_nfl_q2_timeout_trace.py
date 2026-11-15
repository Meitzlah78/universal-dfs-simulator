"""Exact V4 matched replay with a passive event trace; no new policy fitting."""
import csv,gzip,hashlib,json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from simmah_nfl_clock_rebuild_offline import simulate

CONFIG=None
OUT=Path('q2-v4-timeout-audit')
KEYS=['event_index','trial','seconds_before_snap','seconds_at_timeout','distance_before','distance_after','snap_down','next_down','margin','offensive_timeouts_before','defensive_timeouts_before','sampled_interval','hurry_interval']

def init(config):
    global CONFIG
    CONFIG=config

def replay(row):
    game=row['game_id'];count=0
    with gzip.open(OUT/(game+'.csv.gz'),'wt',newline='') as f:
        writer=csv.writer(f);writer.writerow(['game_id','seed']+KEYS)
        for slot,seed in enumerate([17311,29107]):
            def record(d):
                nonlocal count
                for values in zip(*(d[k] for k in KEYS)):
                    writer.writerow([game,seed]+list(values));count+=1
            key=int(hashlib.sha256(f'{game}|{seed}'.encode()).hexdigest()[:16],16)
            result=simulate(512,key,CONFIG['clock'],CONFIG['decision'],CONFIG['parameters'],management_policy='late-half-management-v4',timeout_trace=record)
            if result!=row['batches'][slot]:raise ValueError('Instrumentation changed V4 outputs: '+game)
    return game,count

def main():
    OUT.mkdir(exist_ok=True)
    config=json.load(open('late-half-results/frozen_inputs.json'));rows=json.load(open('late-half-v4-results/game_batches.json'));counts={}
    with ProcessPoolExecutor(max_workers=4,initializer=init,initargs=(config,)) as pool:
        for future in as_completed([pool.submit(replay,r) for r in rows]):
            game,count=future.result();counts[game]=count
            if len(counts)%25==0:print(f'Exact V4 trace {len(counts)}/285',flush=True)
    import pandas as pd
    events=pd.concat([pd.read_csv(p) for p in sorted(OUT.glob('2024_*.csv.gz'))],ignore_index=True)
    denom=285*1024
    def groups(column):
        return {str(k):{'count':int(len(g)),'events_per_game':float(len(g)/denom)} for k,g in events.groupby(column,observed=True)}
    events['clock_bin']=pd.cut(events.seconds_at_timeout,[0,15,30,45,50,65,70],include_lowest=True)
    events['field_bin']=pd.cut(events.distance_after,[0,20,40,50,65],include_lowest=True)
    report={'games':285,'trials':denom,'events':len(events),'timeouts_per_game':len(events)/denom,'instrumentation_parity':'Every saved batch dictionary exactly matches all 570 original V4 batches',
        'clock_at_call':groups('clock_bin'),'field_after_play':groups('field_bin'),'next_down':groups('next_down'),'budget_before_call':groups('offensive_timeouts_before'),
        'last_timeout_on_early_down':float(((events.offensive_timeouts_before==1)&(events.next_down<=2)).sum()/denom),
        'calls_outside_fg_range':float((events.distance_after>40).sum()/denom),
        'call_clock_range':[float(events.seconds_at_timeout.min()),float(events.seconds_at_timeout.max())],
        'zero_or_negative_runoff_saved':int((events.hurry_interval<=5).sum()),
        'timestamp_semantics':'Policy thresholds use pre-snap seconds; call timestamps subtract fixed five live seconds. Field and next down are after play.',
        'source_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['simmah_nfl_clock_rebuild_offline.py',__file__]},'2025':'not opened','production':'unchanged'}
    (OUT/'summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)

if __name__=='__main__':main()
