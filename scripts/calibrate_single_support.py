"""Offline role-ownership calibration of enumerated single-game NPZ support.

Targets JSON: {player_ids: [...], special: [...], flex: [...], source: ...}.
Probabilities must use [0,1] units; missing targets are never inferred.
"""
import argparse,hashlib,json,sys,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_single_calibration import calibrate_role_weights


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--support',type=Path,required=True,help='NPZ containing indices and probabilities')
    p.add_argument('--player-ids',type=Path,required=True,help='Ordered support player IDs JSON')
    p.add_argument('--targets',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True,help='New NPZ file, never overwritten')
    p.add_argument('--feasibility-seconds',type=float,default=5)
    p.add_argument('--max-iterations',type=int,default=500)
    p.add_argument('--tolerance',type=float,default=1e-6)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Refusing to overwrite output')
    ids=json.loads(a.player_ids.read_text());t=json.loads(a.targets.read_text());target_ids=t['player_ids']
    if not all(isinstance(i,str) and i for i in ids+target_ids) or len(set(ids))!=len(ids) or len(set(target_ids))!=len(target_ids) or set(ids)!=set(target_ids):
        raise ValueError('Support and target player IDs must be unique, nonempty and match exactly')
    if not t.get('source'):raise ValueError('Explicit target source required')
    special=np.asarray(t['special'],float);flex=np.asarray(t['flex'],float)
    if special.shape!=(len(target_ids),) or flex.shape!=(len(target_ids),):raise ValueError('One target per player and role required')
    order=np.array([target_ids.index(i) for i in ids]);special=special[order];flex=flex[order]
    with np.load(a.support,allow_pickle=False) as f:picks=f['indices'];prior=f['probabilities']
    started=time.perf_counter()
    r=calibrate_role_weights(picks,prior,special,flex,tolerance=a.tolerance,max_iterations=a.max_iterations,feasibility_seconds=a.feasibility_seconds)
    meta={'offline_only':True,'method':'KL role-marginal dual projection','target_provenance':t,
        'diagnostics':r.diagnostics,'elapsed_seconds':time.perf_counter()-started,
        'configuration':{'tolerance':a.tolerance,'max_iterations':a.max_iterations,'feasibility_seconds':a.feasibility_seconds},
        'source_sha256':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in [('support',a.support),('player_ids',a.player_ids),('targets',a.targets)]}}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation only after the solution has passed residual checks.
    with a.output.open('xb') as handle:
        np.savez(handle,indices=picks,probabilities=r.weights,prior=prior,player_ids=np.asarray(ids),
            special_targets=special,flex_targets=flex,special_achieved=r.special_ownership,
            flex_achieved=r.flex_ownership,metadata_json=np.asarray(json.dumps(meta,allow_nan=False)))
    print(json.dumps(meta,indent=2))

if __name__=='__main__':main()
