"""Archive and validate canonical offline role-ownership feeds, never fetch them."""
import argparse,hashlib,json,os,sys,tempfile,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_ownership_ingest import ingest_ownership,require_calibratable


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--feed',type=Path,required=True);p.add_argument('--format',choices=['json','csv'],required=True)
    p.add_argument('--metadata',type=Path,required=True);p.add_argument('--slate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-sha256')
    p.add_argument('--tolerance',type=float,default=1e-6)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Refusing to overwrite ingestion artifact')
    raw=a.feed.read_bytes();metadata_raw=a.metadata.read_bytes();slate_raw=a.slate.read_bytes()
    files={'raw_feed.'+a.format:raw,'raw_metadata.json':metadata_raw,'raw_site_slate.json':slate_raw}
    error=None;payload=None
    try:
        payload=ingest_ownership(raw,a.format,json.loads(metadata_raw),json.loads(slate_raw),tolerance=a.tolerance,expected_raw_sha256=a.expected_sha256)
        files['normalized_targets.json']=(json.dumps(payload,indent=2,allow_nan=False)+'\n').encode()
        if payload['report']['predictive_eligible']:
            special,flex=require_calibratable(payload)
            targets={'site':payload['identity']['site_id'],'slate_id':payload['identity']['slate_id'],
                'player_ids':payload['player_ids'],'special':special.tolist(),'flex':flex.tolist(),
                'source':{'raw_sha256':payload['raw_sha256'],'metadata':payload['metadata'],'ingested_utc':payload['ingested_utc']}}
            files['calibration_targets.json']=(json.dumps(targets,indent=2,allow_nan=False)+'\n').encode()
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
    report={'artifact_type':'offline_ownership_ingestion','offline_only':True,
        'ingestion_status':'failed' if error else 'parsed','error':error,
        'calibration_ready':False if error else payload['report']['calibration_ready'],
        'predictive_eligible':False if error else payload['report']['predictive_eligible'],
        'feasibility':'not_run','expected_sha256':a.expected_sha256,'tolerance':a.tolerance}
    files['report.json']=(json.dumps(report,indent=2,allow_nan=False)+'\n').encode()
    files['STATUS']=b'failed\n' if error else b'parsed\n'
    files['hashes.json']=json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in files.items()},indent=2).encode()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.ownership-ingest-',dir=a.output.parent)
    try:
        with os.fdopen(fd,'wb') as handle:
            with zipfile.ZipFile(handle,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for name,data in files.items():z.writestr(name,data)
            handle.flush();os.fsync(handle.fileno())
        # Same-filesystem hard link gives atomic publication and no-overwrite.
        # An existence check followed by rename alone would leave a race.
        os.link(tmp,a.output)
    finally:
        os.unlink(tmp)
    print(json.dumps(report,indent=2))
    return 1 if error else (0 if report['predictive_eligible'] else 2)

if __name__=='__main__':sys.exit(main())
