"""Offline field sensitivity run from saved inputs; never exports site entries."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from simmah_nba_random_field import build_randomized_field


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool',type=Path,required=True)
    parser.add_argument('--field-scenarios',type=Path,required=True,help='NPY: saved field-construction outcomes, NOT evaluation outcomes')
    parser.add_argument('--popularity',type=Path,required=True,help='NPY: weights aligned to pool rows')
    parser.add_argument('--site',choices=['dk','fd'],required=True)
    parser.add_argument('--contest-entries',type=int,required=True)
    parser.add_argument('--opponent-entries',type=int,required=True)
    parser.add_argument('--randomness',type=float,default=0)
    parser.add_argument('--seed',type=int,default=83)
    parser.add_argument('--support-target',type=int,default=10000)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    sources={name:path.read_bytes() for name,path in [('pool',args.pool),('field_scenarios',args.field_scenarios),('popularity',args.popularity)]}
    import io
    pool=pd.read_parquet(io.BytesIO(sources['pool'])) if args.pool.suffix=='.parquet' else pd.read_csv(io.BytesIO(sources['pool']),dtype={'Player ID':str})
    pool.attrs['platform']='DraftKings' if args.site=='dk' else 'FanDuel'
    result=build_randomized_field(pool,np.load(io.BytesIO(sources['field_scenarios']),allow_pickle=False),
        np.load(io.BytesIO(sources['popularity']),allow_pickle=False),contest_entries=args.contest_entries,
        opponent_entries=args.opponent_entries,randomness_pct=args.randomness,seed=args.seed,support_target=args.support_target)
    args.output.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(args.output/'field.npz',**{k:v for k,v in result.items() if isinstance(v,np.ndarray)})
    metadata={k:result[k] for k in ['settings','diagnostics']}
    metadata['player_ids']=pool['Player ID'].astype(str).tolist()
    metadata['source_sha256']={k:hashlib.sha256(v).hexdigest() for k,v in sources.items()}
    try:metadata['code_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[1],text=True).strip()
    except (OSError,subprocess.CalledProcessError):metadata['code_commit']=None
    metadata['implementation_sha256']={name:hashlib.sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest() for name in ['simmah_nba_random_field.py','simmah_nba_candidates.py','simmah_nba_rules.py']}
    metadata['artifact_scope']='Offline field experiment only; not a complete build snapshot or publishable export'
    (args.output/'report.json').write_text(json.dumps(metadata,indent=2)+'\n')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.iterdir())}
    (args.output/'hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(json.dumps(result['diagnostics'],indent=2))

if __name__=='__main__':main()
