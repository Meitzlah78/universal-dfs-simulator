"""Local checkpoint-copy cost only, not a hosted page-switch benchmark."""
import argparse,json,sys,time
from pathlib import Path
from statistics import median
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from simmah_session_workspaces import checkpoint,restore_checkpoint


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    rng=np.random.default_rng(801)
    state={'evaluation':rng.normal(size=(10000,275)),'construction':rng.normal(size=(10000,275)),
        'portfolio':pd.DataFrame({'Player':['A','B'],'Score':[123.,124.]}),'export_bytes':b'complete assigned entries'}
    app=SimpleNamespace(session_state=state);prepared=checkpoint(app)
    timings={'before':[],'after':[]}
    for _ in range(7):
        for label in ('before','after'):
            started=time.perf_counter()
            captured=checkpoint(app) if label=='before' else prepared
            target=SimpleNamespace(session_state={});restore_checkpoint(target,captured)
            timings[label].append(time.perf_counter()-started)
            np.testing.assert_array_equal(target.session_state['evaluation'],state['evaluation'])
            assert target.session_state['export_bytes']==state['export_bytes']
            assert not np.shares_memory(target.session_state['evaluation'],captured['values']['evaluation'])
    report={'classification':'SYNTHETIC_CHECKPOINT_COPY_AND_RESTORE','matrix_bytes':state['evaluation'].nbytes+state['construction'].nbytes,
        'runs_seconds':timings,'median_seconds':{k:median(v) for k,v in timings.items()},'exact_restoration':True,
        'scope':'Detached capture already produced by autosave; excludes fingerprinting, UI rendering, data refresh, cloud I/O and the complete site switch.'}
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
