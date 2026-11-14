import gzip
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import pandas as pd
import simmah_nba_shadow_capture as shadow
from simmah_nba_shadow_worker import run

class ShadowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'SIMMAH_NBA_SHADOW_CAPTURE':'1'});self.env.start();self.addCleanup(self.env.stop)
        with shadow._LOCK:shadow._RECEIPTS.clear();shadow._HEALTH.clear()
        self.pool=pd.DataFrame([{'Player ID':'1','Name':'A','Team':'MIL','Projection':30.,'Projected Minutes':28.}])
    def tearDown(self):
        if shadow._EXECUTOR is not None:
            shadow._EXECUTOR.shutdown(wait=True);shadow._EXECUTOR=None
    def test_disabled_mode_does_not_queue_or_capture(self):
        with patch.dict(os.environ,{'SIMMAH_NBA_SHADOW_CAPTURE':'0'}),patch.object(shadow,'_freeze') as freeze:
            self.assertIsNone(shadow.begin_build_capture(self.pool,self.pool,settings={},model={}))
            self.assertEqual(shadow.read_json_response(io.BytesIO(b'{"a":1}'),'source'),{'a':1})
            freeze.assert_not_called();self.assertEqual(shadow.health()['receipt_sources'],0)
    def test_receipt_precedes_parse_and_bad_json_does_not_erase_receipt(self):
        with self.assertRaises(json.JSONDecodeError):shadow.read_json_response(io.BytesIO(b'bad'),'source')
        self.assertEqual(shadow._RECEIPTS['source']['raw'],b'bad')
    def test_frozen_inputs_detach_caller_mutations_and_raw_hashes(self):
        raw=b'{ "players" : [1] }';shadow.remember_response('source',raw)
        settings={'v':[1]};frozen,receipts,cid=shadow._freeze(self.pool,self.pool,settings,{})
        self.pool.loc[0,'Projection']=99.;settings['v'].append(2)
        record=json.loads(frozen)
        self.assertEqual(record['baseline_forecasts'][0]['Projection'],30.)
        self.assertEqual(record['settings']['v'],[1])
        self.assertLessEqual(receipts[0]['observed_at'],record['frozen_at'])
        with tempfile.TemporaryDirectory() as root:
            r=Path(root);receipt=receipts[0]
            (r/(receipt['sha256']+'.response.gz')).write_bytes(gzip.compress(raw))
            p=r/(cid+'.capture.json');p.write_bytes(frozen)
            result=run(p)
            self.assertEqual(result['capture_id'],cid)
            self.assertIsNone(result['predictions']);self.assertIsNone(result['allocation_conflict'])
            self.assertFalse(result['production_modified'])
    def test_real_background_sidecar_records_blocker_without_mutating_pool(self):
        shadow.remember_response('source',b'{"players":[]}')
        before=self.pool.copy(deep=True)
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'SIMMAH_NBA_SHADOW_DIRECTORY':root}):
            cid=shadow.begin_build_capture(self.pool,self.pool,settings={},model={})
            self.assertIsNotNone(cid)
            shadow._EXECUTOR.shutdown(wait=True);shadow._EXECUTOR=None
            result=json.loads((Path(root)/(cid+'.result.json')).read_text())
            self.assertEqual(result['status'],'uncertified_pool')
            pd.testing.assert_frame_equal(before,self.pool)
            self.assertEqual(shadow.health()['captures_persisted'],1)
    def test_queue_full_returns_immediately(self):
        with patch.object(shadow,'_PENDING') as pending:
            pending.acquire.return_value=False
            self.assertIsNone(shadow.begin_build_capture(self.pool,self.pool,settings={},model={}))
            pending.acquire.assert_called_once_with(blocking=False)
    def test_disk_failure_cannot_raise_into_build(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'SIMMAH_NBA_SHADOW_DIRECTORY':root}),patch.object(shadow,'_persist_and_run',side_effect=OSError('disk')):
            cid=shadow.begin_build_capture(self.pool,self.pool,settings={},model={})
            shadow._EXECUTOR.shutdown(wait=True);shadow._EXECUTOR=None
            event=json.loads((Path(root)/(cid+'.failure.json')).read_text())
            self.assertEqual(event['reason'],'capture_or_worker_failed')
    def test_receipt_overflow_is_bounded(self):
        with patch.object(shadow,'_MAX_RAW',5):
            shadow.remember_response('a',b'1234');shadow.remember_response('b',b'1234')
            self.assertEqual(list(shadow._RECEIPTS),['b'])
    def test_freeze_failure_is_nonfatal(self):
        with patch.object(shadow,'_freeze',side_effect=ValueError('bad input')):
            self.assertIsNone(shadow.begin_build_capture(self.pool,self.pool,settings={},model={}))
            self.assertEqual(shadow.health()['freeze_or_submit_failed'],1)

if __name__=='__main__':unittest.main()
