"""Export an existing Showdown evaluation session, without rerunning it.

This is an evaluation bundle, not a complete staged build snapshot.
"""
import hashlib
import io
import json
import zipfile
from datetime import datetime,timezone
import numpy as np
import pandas as pd

SLOTS=['Captain','Flex1','Flex2','Flex3','Flex4','Flex5']

def _json_value(value):
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,(datetime,pd.Timestamp)):return value.isoformat()
    raise TypeError(f'Cannot serialize {type(value).__name__}')

def comparison_bundle(candidates,pool,field,scenarios,contest):
    for name,frame in [('candidates',candidates),('pool',pool),('field',field),('scenarios',scenarios)]:
        if not isinstance(frame,pd.DataFrame) or frame.empty:raise ValueError(f'Missing {name}')
    if not scenarios.columns.is_unique or not all(isinstance(c,str) for c in scenarios.columns):
        raise ValueError('Unique player-name scenario columns required')
    for frame in (candidates,field):
        if not set(SLOTS)<=set(frame):raise ValueError('Showdown roster columns missing')
        if not set(frame[SLOTS].to_numpy().ravel())<=set(scenarios.columns):
            raise ValueError('Lineup player missing from saved simulations')
    arrays=scenarios.to_numpy(copy=True)
    if not np.issubdtype(arrays.dtype,np.number) or not np.isfinite(arrays).all():raise ValueError('Finite numeric simulations required')
    def json_bytes(obj):return (json.dumps(obj,indent=2,allow_nan=False,default=_json_value)+'\n').encode()
    stream=io.BytesIO();np.savez(stream,points=arrays)
    files={
        'candidates.csv':candidates.to_csv(index=False).encode(),
        'player_pool.csv':pool.to_csv(index=False).encode(),
        'baseline_field.csv':field.to_csv(index=False).encode(),
        'scenarios.npz':stream.getvalue(),
        'scenario_player_names.json':json_bytes(scenarios.columns.tolist()),
        'scenario_ids.json':json_bytes(scenarios.index.tolist()),
        'contest.json':json_bytes(contest),
        'pool_attrs.json':json_bytes(dict(pool.attrs)),
    }
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    files['meta.json']=json_bytes({'schema_version':'1.0','artifact_type':'showdown_evaluation_bundle',
        'created_utc':datetime.now(timezone.utc).isoformat(),'candidate_count':len(candidates),
        'scenario_count':len(scenarios),'scenario_shape':list(arrays.shape),'scenario_dtype':str(arrays.dtype),
        'captain_points_multiplier':1.5,'pool_capture':'Current UI pool; original build-time settings/provenance are not guaranteed.',
        'limitations':'Not a complete build snapshot. Saves existing outcomes without regeneration.',
        'content_id':hashlib.sha256(json_bytes(hashes)).hexdigest()})
    hashes['meta.json']=hashlib.sha256(files['meta.json']).hexdigest()
    files['hashes.json']=json_bytes(hashes)
    output=io.BytesIO()
    # Stored ZIP avoids compression CPU cost in the constrained app host.
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as z:
        for name,data in files.items():z.writestr(name,data)
    return output.getvalue()
