import unittest,subprocess,sys,json,tempfile,zipfile,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
import test_ownership_ingest as fixtures

class ArchiveTests(unittest.TestCase):
    def test_success_raw_identity_hashes_bridge_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);s,m,r=fixtures.IngestionTests().fixtures()
            now=datetime.now(timezone.utc)
            m.update(request_started_utc=(now-timedelta(minutes=3)).isoformat(),request_completed_utc=(now-timedelta(minutes=2)).isoformat(),
                last_successful_received_utc=(now-timedelta(minutes=2)).isoformat(),lock_time_utc=(now+timedelta(hours=1)).isoformat())
            feed=json.dumps(r).encode();(root/'feed.json').write_bytes(feed)
            (root/'meta.json').write_text(json.dumps(m));(root/'slate.json').write_text(json.dumps(s))
            cmd=[sys.executable,'scripts/ingest_role_ownership.py','--feed',str(root/'feed.json'),'--format','json',
                '--metadata',str(root/'meta.json'),'--slate',str(root/'slate.json'),'--output',str(root/'bundle.zip')]
            result=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
            original=(root/'bundle.zip').read_bytes()
            with zipfile.ZipFile(root/'bundle.zip') as z:
                self.assertEqual(z.read('raw_feed.json'),feed)
                for name,digest in json.loads(z.read('hashes.json')).items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest)
                target=json.loads(z.read('calibration_targets.json'));self.assertEqual(target['player_ids'],s['player_ids'])
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual((root/'bundle.zip').read_bytes(),original)
    def test_bad_feed_archived_and_unknowns_block_bridge(self):
        for bad in (True,False):
            with self.subTest(malformed=bad),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);s,m,r=fixtures.IngestionTests().fixtures()
                if bad:r[0]['player_id']='not-on-slate'
                else:r.pop()
                feed=json.dumps(r).encode();(root/'feed.json').write_bytes(feed)
                (root/'meta.json').write_text(json.dumps(m));(root/'slate.json').write_text(json.dumps(s))
                cmd=[sys.executable,'scripts/ingest_role_ownership.py','--feed',str(root/'feed.json'),'--format','json',
                    '--metadata',str(root/'meta.json'),'--slate',str(root/'slate.json'),'--output',str(root/'bundle.zip')]
                result=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(result.returncode,1 if bad else 2,result.stderr)
                with zipfile.ZipFile(root/'bundle.zip') as z:
                    self.assertEqual(z.read('raw_feed.json'),feed);self.assertNotIn('calibration_targets.json',z.namelist())
                    report=json.loads(z.read('report.json'));self.assertEqual(report['feasibility'],'not_run')
                    self.assertFalse(report['predictive_eligible'])
