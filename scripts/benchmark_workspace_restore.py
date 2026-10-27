"""Explicit local-only lossless ZIP/chunk recovery capacity benchmark."""
import argparse
import base64
import json
from pathlib import Path
import sys
import tempfile
import time
try:
    import resource
except ImportError:
    resource=None
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import simmah_workspace_backup as backup
import simmah_workspace_persistence as persistence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mib',type=int,default=192)
    parser.add_argument('--output',required=True)
    parser.add_argument('--additional-address-space-bytes',type=int)
    parser.add_argument('--environment',default='isolated local executor, not Streamlit Cloud')
    args=parser.parse_args()
    if not 1<=args.mib<=511:parser.error('Use 1–511 MiB of source data; ZIP overhead counts toward the 512 MiB cap')
    if args.additional_address_space_bytes is not None:
        if args.additional_address_space_bytes<=0 or not sys.platform.startswith('linux') or resource is None:
            parser.error('A positive address-space budget on Linux is required')
        virtual_kib=next(int(line.split()[1]) for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmSize:'))
        _,hard=resource.getrlimit(resource.RLIMIT_AS)
        ceiling=virtual_kib*1024+args.additional_address_space_bytes
        if hard!=resource.RLIM_INFINITY:ceiling=min(ceiling,hard)
        resource.setrlimit(resource.RLIMIT_AS,(ceiling,hard))
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
    report=dict(schema=1,environment=args.environment,synthetic_array_bytes=original.nbytes,
                zip_bytes=len(raw),zip_mib=len(raw)/1024**2,configured_zip_cap_bytes=backup.MAX_BYTES,
                recovery_frames=total,exact_full_array_equal=True,archive_hash_verified=True,seconds=time.monotonic()-start,
                peak_process_rss_bytes=(int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1024 if sys.platform.startswith('linux') else 1) if resource else None),
                additional_address_space_budget=args.additional_address_space_bytes)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
