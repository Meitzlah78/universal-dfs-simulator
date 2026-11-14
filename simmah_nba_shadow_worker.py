"""Isolated shadow adapter/allocator. No live engine, arrays or Streamlit state."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys


def run(path):
    path=Path(path);raw=path.read_bytes();capture=json.loads(raw)
    if capture.get('mode')!='shadow':raise ValueError('Shadow capture required')
    cid=capture['capture_id']
    if not isinstance(cid,str) or re.fullmatch(r'[A-Za-z0-9_-]{1,64}',cid) is None:
        raise ValueError('Invalid capture ID')
    records={};bodies={};duplicates=set()
    for receipt in capture['receipts']:
        digest=receipt['sha256']
        if not isinstance(digest,str) or re.fullmatch(r'[a-f0-9]{64}',digest) is None:raise ValueError('Invalid receipt hash')
        body=gzip.decompress((path.parent/(digest+'.response.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest()!=digest:raise ValueError('Receipt hash mismatch')
        if digest in records:duplicates.add(digest)
        records[digest]=receipt;bodies[digest]=body
    result={'capture_id':cid,'capture_sha256':hashlib.sha256(raw).hexdigest(),
        'status':'uncertified_pool','reasons':capture.get('warnings',[]),
        'allocation_conflict':None,'predictions':None,'production_modified':False}
    requests=capture.get('adapter_requests',[])
    if requests and not isinstance(requests,list):
        result['reason']='MALFORMED_ADAPTER_REQUEST_LIST';requests=[]
    if requests:
        from simmah_nba_shadow_adapters import run_team
        pinned=capture.get('model_source_hashes',{})
        matched=all(pinned.get(name)==hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                    for name in ('simmah_nba_shadow_worker.py','simmah_nba_shadow_adapters.py'))
        from collections import Counter
        valid=lambda r: isinstance(r,dict) and all(isinstance(r.get(k),str) for k in ('game_id','team_id','roster_sha256','history_sha256'))
        counts=Counter((r['game_id'],r['team_id']) for r in requests if valid(r))
        results=[]
        for request in requests:
            if not valid(request):
                results.append({'capture_id':cid,'status':'uncertified_pool','reason':'MALFORMED_ADAPTER_REQUEST','production_modified':False,'qualified_for_evaluation':False})
                continue
            key=(request.get('game_id'),request.get('team_id'))
            requested_hashes={request.get('roster_sha256'),request.get('history_sha256')}
            failure=('MODEL_VERSION_NOT_FROZEN' if not matched else 'DUPLICATE_TEAM_GAME_REQUEST' if counts[key]>1 else 'AMBIGUOUS_RECEIPT_HASH' if requested_hashes & duplicates else None)
            if failure:
                item={'capture_id':cid,'game_id':key[0],'team_id':key[1],'status':'uncertified_pool','reason':failure,'production_modified':False,'qualified_for_evaluation':False}
            else:
                try:payloads={h:json.loads(bodies[h]) for h in requested_hashes}
                except (KeyError,ValueError,TypeError):
                    item={'capture_id':cid,'game_id':key[0],'team_id':key[1],'status':'uncertified_pool','reason':'MISSING_OR_INVALID_SOURCE_PAYLOAD','production_modified':False,'qualified_for_evaluation':False}
                else:item=run_team(capture,request,records,payloads)
            results.append(item)
        result['team_game_results']=results
        if len(results)==1:result.update(results[0])
        else:result['status']='team_game_results'  # Each team has its own terminal state.
    output=path.with_name(cid+'.result.json')
    with output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    return result

if __name__=='__main__':run(sys.argv[1])
