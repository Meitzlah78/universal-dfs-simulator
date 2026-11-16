"""Exact-output worker benchmark; synthetic inputs, no postgame calibration."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from simmah_candidates import summarize_candidates
from simmah_contests import evaluate_contest
from simmah_numeric_workers import scoring_workers


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--outcomes',type=int,default=10000)
    args=parser.parse_args();rng=np.random.default_rng(874)
    names=[str(i) for i in range(275)];slots=['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','DST']
    outcomes=pd.DataFrame(rng.normal(12,8,(args.outcomes,275)).astype(np.float32),columns=names)
    candidates=pd.DataFrame([rng.choice(names,9,False) for _ in range(5000)],columns=slots)
    field=pd.DataFrame([rng.choice(names,9,False) for _ in range(10000)],columns=slots)
    results={};reference=None
    for workers in (1,2,4,4,2,1):
        start=time.perf_counter();summary=summarize_candidates(candidates,outcomes,slots,workers=workers)
        summary_seconds=time.perf_counter()-start;start=time.perf_counter()
        report=evaluate_contest(outcomes,summary,field,slots,100000,[(1,1,1000),(2,100,10),(101,20000,.1)],.05,workers=workers)
        contest_seconds=time.perf_counter()-start
        if reference is None:reference=(summary,report)
        else:
            pd.testing.assert_frame_equal(summary,reference[0],check_exact=True)
            pd.testing.assert_frame_equal(report,reference[1],check_exact=True)
        measurement={'effective_workers':scoring_workers(workers),
            'summary_seconds':summary_seconds,'contest_seconds':contest_seconds,
            'total_seconds':summary_seconds+contest_seconds}
        results.setdefault(str(workers),[]).append(measurement)
        print(json.dumps({workers:measurement}),flush=True)
    payload={'classification':'SYNTHETIC_EXACT_OUTPUT_REPLAY','players':275,'outcomes':args.outcomes,
        'candidates':5000,'opponents':10000,'results':results,'exact_frame_parity':True,
        'scope':'Local numeric scoring only; excludes cold simulation fitting, candidate search, field construction, selector and hosted UI. No reduction in simulations, candidates or field size.'}
    Path(args.output).write_text(json.dumps(payload,indent=2)+'\n')

if __name__=='__main__':main()
