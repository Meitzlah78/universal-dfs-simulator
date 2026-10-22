"""Enumerate offline single-game support; never changes or exports live entries."""
import argparse,hashlib,json,sys,time,io,tempfile,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from simmah_single_exhaustive import prepare,enumerate_lineups


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool',type=Path,required=True)
    parser.add_argument('--site',choices=['dk','fd'],required=True)
    parser.add_argument('--min-salary',type=float,default=0)
    parser.add_argument('--output',type=Path,help='New directory for chunked NPZ support. Omit for count-only.')
    parser.add_argument('--special-player-ids',nargs='+',help='Current-slate Captain/MVP IDs; FLEX stays unrestricted.')
    args=parser.parse_args()
    raw=args.pool.read_bytes()
    pool=pd.read_parquet(io.BytesIO(raw)) if args.pool.suffix=='.parquet' else pd.read_csv(io.BytesIO(raw),dtype={'Player ID':str})
    state=prepare(pool,args.site,min_salary=args.min_salary)
    metadata={'schema_version':'1.0','artifact_type':'offline_exhaustive_single_game_support','live_enabled':False,
      'special_player_ids':args.special_player_ids,'site':args.site,'min_salary':args.min_salary,'salary_cap':50000 if args.site=='dk' else 60000,
      'special_salary_multiplier':1.5,'special_points_multiplier':1.5,
      'special_salary_source':'CaptainSalary' if args.site=='dk' and 'CaptainSalary' in pool else '1.5 * Salary',
      'both_teams_required':True,'flex_order':'ascending original pool-row index','eligible_players':state['eligible_players'],
      'possible_special_assignments_before_salary_and_team_filters':state['special_role_assignments'],
      'pool_sha256':hashlib.sha256(raw).hexdigest(),'player_ids':pool['Player ID'].astype(str).tolist(),
      'limitations':'Exhaustive legal support only. No ownership weighting, realistic duplicates, contest scoring or ROI validation.'}
    temporary=None
    if args.output:
        if args.output.exists():raise ValueError('Refusing to overwrite an existing output')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        temporary=Path(tempfile.mkdtemp(prefix='.exhaustive-',dir=args.output.parent))
        (temporary/'STATUS').write_text('incomplete\n')
    started=time.perf_counter();count=0;chunks=0
    try:
        for indices,salary in enumerate_lineups(pool,args.site,min_salary=args.min_salary,special_player_ids=args.special_player_ids):
            count+=len(indices)
            if temporary:np.savez(temporary/f'lineups_{chunks:06d}.npz',indices=indices,salary=salary)
            chunks+=1
        metadata.update(legal_lineups=count,elapsed_seconds=time.perf_counter()-started,chunks=chunks,exhaustive_complete=True)
        if temporary:
            (temporary/'meta.json').write_text(json.dumps(metadata,indent=2)+'\n')
            (temporary/'STATUS').write_text('complete\n')
            hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(temporary.iterdir())}
            (temporary/'hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
            # Exclusive mkdir reserves destination; move children only after
            # enumeration succeeds. STATUS moves last to gate consumption.
            args.output.mkdir(exist_ok=False)
            for p in sorted(temporary.iterdir(),key=lambda p:p.name=='STATUS'):p.rename(args.output/p.name)
            temporary.rmdir()
        print(json.dumps(metadata,indent=2))
    except BaseException:
        if temporary and temporary.exists():(temporary/'STATUS').write_text('failed\n')
        raise

if __name__=='__main__':main()
