"""Explicit local-only lossless ZIP/chunk recovery capacity benchmark."""
import argparse
import base64
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import simmah_workspace_backup as backup
import simmah_workspace_persistence as persistence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mib',type=int,default=192)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not 1<=args.mib<=511:parser.error('Use 1–511 MiB of source data; ZIP overhead counts toward the 512 MiB cap')
    start=time.monotonic()
    original=np.random.default_rng(83).integers(0,256,args.mib*1024*1024,dtype=np.uint8)
    payload=dict(record=dict(id='capacity-test',name='synthetic.csv',data='synthetic'),
                 checkpoint=dict(values=dict(outcomes=original),uploads={},artifacts={}))
    raw=backup.pack(payload)
    ref=dict(id='capacity-test',token='b'*32,digest=backup.digest(raw),bytes=len(raw))
    state={'_slate_backup_owner':'a'*32,'_slate_backup_restore':ref}
    with tempfile.TemporaryDirectory() as root,patch.object(backup,'ROOT',Path(root)):
        total=(len(raw)+backup.RECOVERY_CHUNK_BYTES-1)//backup.RECOVERY_CHUNK_BYTES
        for i in range(total):
            part=raw[i*backup.RECOVERY_CHUNK_BYTES:(i+1)*backup.RECOVERY_CHUNK_BYTES]
            persistence.receive_backup_part(state,dict(id='capacity-roundtrip',index=i,total=total,data=base64.b64encode(part).decode()))
        restored=state['_slate_pending']['_session_checkpoint']['values']['outcomes']
        if not np.array_equal(restored,original):raise ValueError('Restored array differs')
    report=dict(schema=1,environment='isolated local executor, not Streamlit Cloud',synthetic_array_bytes=original.nbytes,
                zip_bytes=len(raw),zip_mib=len(raw)/1024**2,configured_zip_cap_bytes=backup.MAX_BYTES,
                recovery_frames=total,exact_full_array_equal=True,archive_hash_verified=True,seconds=time.monotonic()-start)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
