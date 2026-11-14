"""Isolated input-check sidecar. No candidate is allowed to alter live outputs."""
import hashlib
import json
from pathlib import Path
import sys


def run(path):
    path=Path(path);raw=path.read_bytes();capture=json.loads(raw)
    if capture.get('mode')!='shadow':raise ValueError('Shadow capture required')
    for receipt in capture['receipts']:
        from gzip import decompress
        body=decompress((path.parent/(receipt['sha256']+'.response.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest()!=receipt['sha256']:raise ValueError('Receipt hash mismatch')
    # Honest blocker: raw receipt availability does not certify eligibility,
    # complete team membership, current-role priors or learned bound support.
    result={'capture_id':capture['capture_id'],'capture_sha256':hashlib.sha256(raw).hexdigest(),
        'status':'uncertified_pool','reasons':capture['warnings'],
        'allocation_conflict':None,'predictions':None,'production_modified':False}
    output=path.with_name(capture['capture_id']+'.result.json')
    with output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    return result

if __name__=='__main__':run(sys.argv[1])
