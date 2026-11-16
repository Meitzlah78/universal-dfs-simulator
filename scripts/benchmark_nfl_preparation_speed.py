"""Paired cold/warm replay with frozen inputs and an explicit baseline engine."""
import argparse,importlib.util,json,subprocess,sys,tempfile,time,types,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
import simmah_nfl_engine as engine
import simmah_simulation_store as store


def main():
    parser=argparse.ArgumentParser()
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--fit-spec');source.add_argument('--archive')
    parser.add_argument('--baseline-ref',default='030b4086f54210123df546bc8824a4026c445b8f')
    parser.add_argument('--output',required=True);args=parser.parse_args()
    if args.archive:
        with zipfile.ZipFile(args.archive) as z:
            spec=json.loads(z.read('solver/cache/prepared/manifest.json'))['fit_spec']
    else:spec=json.loads(Path(args.fit_spec).read_text())
    raw=subprocess.check_output(['git','show',args.baseline_ref+':simmah_nfl_engine.py'],text=True)
    old=types.ModuleType('baseline_nfl_engine');exec(compile(raw,'baseline_nfl_engine.py','exec'),old.__dict__)
    pool=pd.DataFrame(spec['players']);outputs=[];results=[]
    learned=spec.get('learned_parameters',{})
    model={'parameters':learned,'players':{},'version':'frozen-benchmark-inputs'} if learned else None
    for label,fn in [('before',old.simulate_stat_lines),('after',engine.simulate_stat_lines)]:
        with tempfile.TemporaryDirectory() as cache,patch.object(engine,'simulate_stat_lines',fn),patch.object(store,'simulate_stat_lines',fn),patch('simmah_nfl_learning.model_for_date',return_value=model):
            kwargs=dict(count=10000,pilot_n=spec.get('pilot_n',1024),iterations=spec.get('iterations',8),
                correlation_strength=spec['correlation_strength'],weather_by_team=spec['weather'],
                market_targets={team:[value] for team,value in spec['market_targets'].items()})
            started=time.perf_counter();out=store.prepare_simulations(pool,spec['roles'],spec['platform'],cache,**kwargs)
            seconds=time.perf_counter()-started;started=time.perf_counter()
            warm=store.prepare_simulations(pool,spec['roles'],spec['platform'],cache,**kwargs)
            warm_seconds=time.perf_counter()-started
            for key in ('evaluation','construction','fit_report'):pd.testing.assert_frame_equal(out[key],warm[key],check_exact=True)
            params=json.loads((Path(cache)/'fits'/(out['metadata']['fit_key']+'.json')).read_text())['payload']['parameters']
            outputs.append((out,params))
            results.append(dict(label=label,total_seconds=seconds,warm_seconds=warm_seconds,timings=out['metadata']['timings']))
            print(json.dumps(results[-1]),flush=True)
    for key in ('evaluation','construction','fit_report'):pd.testing.assert_frame_equal(outputs[0][0][key],outputs[1][0][key],check_exact=True)
    assert outputs[0][1]==outputs[1][1]
    Path(args.output).write_text(json.dumps(dict(baseline_ref=args.baseline_ref,players=len(pool),platform=spec['platform'],
        results=results,exact_parameters_reports_and_outcomes=True,
        scope='Local paired numerical preparation, excludes network, candidate/field search, selector and hosted UI.'),indent=2)+'\n')

if __name__=='__main__':main()
