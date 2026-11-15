"""Passive matched-ten-game V5 event invariant check; not new validation data."""
import hashlib,json
from pathlib import Path
import numpy as np
from simmah_nfl_clock_rebuild_offline import simulate,POLICY_VERSION


def main():
    if POLICY_VERSION!='late-half-management-v5':raise ValueError('Frozen V5 checker only')
    f=json.load(open('late-half-results/frozen_inputs.json'));rows=json.load(open('late-half-v5-results/game_batches.json'))[:10]
    counts={'events':0,'reserved_last_timeout':0,'reserved_on_late_down':0,'reserved_final_fg_range':0};clocks=[]
    for row in rows:
        for slot,seed in enumerate([17311,29107]):
            def record(d):
                c=d['seconds_at_timeout'];budget=d['offensive_timeouts_before'];field=d['distance_after'];down=d['next_down']
                allowed=(down>=3)|((field<=40)&(c<=15))
                if not ((c>0)&(c<=50)&(field<65)&(budget>0)&(budget<=3)&(d['margin']<21)&(d['hurry_interval']>5)&((budget>1)|allowed)).all():
                    raise ValueError('V5 timeout event violates frozen policy')
                clocks.extend(c.tolist());counts['events']+=len(c);counts['reserved_last_timeout']+=int((budget==1).sum())
                counts['reserved_on_late_down']+=int(((budget==1)&(down>=3)).sum())
                counts['reserved_final_fg_range']+=int(((budget==1)&(down<3)&(field<=40)&(c<=15)).sum())
            key=int(hashlib.sha256(f"{row['game_id']}|{seed}".encode()).hexdigest()[:16],16)
            result=simulate(512,key,f['clock'],f['decision'],f['parameters'],management_policy=POLICY_VERSION,timeout_trace=record)
            if result!=row['batches'][slot]:raise ValueError('Passive check changed saved V5 outputs')
    report={'scope':'First ten lexically sorted 2024 labels; two seeds and 512 draws each; diagnostic subset reused from V5 baseline',
        'games':len(rows),'trials':len(rows)*1024,'counts':counts,'call_clock_range':[min(clocks),max(clocks)],
        'invariant_failures':0,'instrumentation_parity':'Every result dictionary exactly matches all 20 saved V5 batches',
        'driver_sha256':hashlib.sha256(Path('simmah_nfl_clock_rebuild_offline.py').read_bytes()).hexdigest(),
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'2025':'not opened','production':'unchanged'}
    Path('late-half-v5-results/event_invariants.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)

if __name__=='__main__':main()
