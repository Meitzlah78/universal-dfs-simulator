"""Import frozen pregame source rates from saved calibration bundles.

Usage: python scripts/import_nba_rate_snapshots.py bundle.zip [bundle.zip ...]
New builds embed a source snapshot before applying any learned updates. Older
bundles are deliberately not dated using their export filenames: an export can
occur after a game, and would not prove when its provider rates were fetched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_individual_learning import validate_individual


def import_bundle(path, root):
    with zipfile.ZipFile(path) as bundle:
        pool=json.loads(bundle.read('inputs/player_pool.json'))
    snapshot=pool.get('attrs',{}).get('nba_individual_rate_snapshot')
    if not snapshot:
        return {'status':'skipped','reason':'No timestamped pregame source snapshot','file':str(path)}
    validate_individual([], [snapshot], '9999-12-31')
    payload=(json.dumps(snapshot,sort_keys=True,indent=2)+'\n').encode()
    digest=hashlib.sha256(payload).hexdigest()
    directory=Path(root)/'individual_rate_snapshots';directory.mkdir(parents=True,exist_ok=True)
    destination=directory/(digest+'.json')
    destination.write_bytes(payload)
    return {'status':'imported','players':len(snapshot['players']),'file':destination.name}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundles',nargs='+')
    parser.add_argument('--model-root',default=str(Path(__file__).resolve().parents[1]/'data/nba_models'))
    args=parser.parse_args()
    for bundle in args.bundles:
        print(json.dumps(import_bundle(bundle,args.model_root)))
