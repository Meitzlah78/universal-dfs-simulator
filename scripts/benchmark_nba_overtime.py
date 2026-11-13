"""Paired frozen-input eager/lazy rotation timing; never submits live entries."""
import argparse,gc,hashlib,io,json,sys,time,zipfile
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from simmah_nba_overtime_rotations import OvertimeRotations
from simmah_nba_pregame import PregameEngine
from simmah_nba_engine import EventRates
from simmah_nba_rules import rules_for


class Eager:
    def __new__(cls,*args,**kwargs):return OvertimeRotations(*args,**kwargs).materialize()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive');p.add_argument('--simulations',type=int,default=10000)
    p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--output',required=True);args=p.parse_args()
    path=Path(args.archive)
    with zipfile.ZipFile(path) as outer:
        raw=outer.read('original_build.zip') if 'original_build.zip' in outer.namelist() else path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest=json.loads(z.read('manifest.json'))
        for name,info in manifest['files'].items():
            if hashlib.sha256(z.read(name)).hexdigest()!=info['sha256']:raise ValueError('Source archive mismatch')
        meta=json.loads(z.read('inputs/player_pool.json'))
        pool=pd.DataFrame(meta['rows']);pool.attrs=meta['attrs']
        markets=json.loads(z.read('inputs/markets.json'))
    rates=EventRates(**json.loads((ROOT/'data/nba_models/event-rates-before-2026-04-09.json').read_text())['rates'])
    records=[]
    for repeat in range(args.repeats):
        reference=None;reference_report=None;pair=[]
        for arm in (['eager','lazy'] if repeat%2==0 else ['lazy','eager']):
            gc.collect()
            engine=PregameEngine(pool,markets,rates,platform=rules_for(pool)['platform'],parallel=False)
            start=time.perf_counter();draws=[];reports=[]
            with patch('simmah_nba_overtime_rotations.OvertimeRotations',Eager) if arm=='eager' else nullcontext():
                for seed in [83,1092,2100]:
                    draws.append(engine(args.simulations,seed));reports.append(engine.last_report)
            seconds=time.perf_counter()-start
            if reference is None:reference=draws;reference_report=reports
            else:
                for a,b in zip(reference,draws):np.testing.assert_array_equal(a,b)
                if reports!=reference_report:raise AssertionError('Game report parity failed')
            record={'repeat':repeat,'arm':arm,'seconds':seconds,
                'draw_sha256':[hashlib.sha256(d.tobytes()).hexdigest() for d in draws]}
            records.append(record);pair.append(record);print(json.dumps(record),flush=True)
        if pair[0]['draw_sha256']!=pair[1]['draw_sha256']:raise AssertionError('Score parity failed')
    means={arm:float(np.mean([r['seconds'] for r in records if r['arm']==arm])) for arm in ['eager','lazy']}
    result={'scope':'Frozen archived NBA inputs, current pregame engine, three independent 10,000-draw phases. Sequential game execution on benchmark hardware; not live host latency or archived-score reproduction.',
        'archive':path.name,'players':len(pool),'games':len(engine.games),'simulations_per_set':args.simulations,
        'repeats':args.repeats,'records':records,'mean_seconds':means,
        'simulation_reduction_pct':100*(1-means['lazy']/means['eager']),
        'exact_scores_and_game_reports':True,'max_overtimes_unchanged':10,
        'candidate_target_unchanged':5000,'field_support_target_unchanged':10000}
    Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()
