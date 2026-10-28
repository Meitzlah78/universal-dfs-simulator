import io
from contextlib import nullcontext
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import simmah_workspace_cloud as cloud
import simmah_workspace_backup as backup
import simmah_workspace_persistence as persistence


class FakeS3:
    objects = {}
    puts = []
    def __init__(self, config):
        self.bucket = 'test'; self.prefix = 'simmah-inputs'; self.client = self
    def head_object(self, Bucket, Key):
        from botocore.exceptions import ClientError
        if Key not in self.objects:
            raise ClientError({'Error':{'Code':'404'}}, 'HeadObject')
        return {'Metadata':{'sha256':backup.digest(self.objects[Key])}}
    def put(self, owner, key, raw):
        self.objects[f'{self.prefix}/{owner}/{key}'] = bytes(raw)
        self.puts.append((key,len(raw)))
    def get(self, owner, key):
        return self.objects[f'{self.prefix}/{owner}/{key}']


class CloudWorkspaceTests(unittest.TestCase):
    def setUp(self):
        FakeS3.objects = {};FakeS3.puts = []
        self.patch = patch.object(cloud, 'S3Backup', FakeS3)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.owner = 'a'*32
    def payload(self, salary=49000):
        return dict(record=dict(id='dk',name='entries.csv',data='original'),
                    checkpoint=dict(values=dict(salary=salary,
                       outcomes=np.random.default_rng(5).normal(size=(10000,100)))))
    def ref(self, raw):
        return dict(token='b'*32,digest=backup.digest(raw),bytes=len(raw),id='dk',revision=1)
    def test_settings_edit_reuses_large_simulation_segment(self):
        raw = backup.pack(self.payload())
        first = cloud.save({'bucket':'test'},self.owner,raw,self.ref(raw))
        first_bytes = sum(n for key,n in FakeS3.puts)
        FakeS3.puts = []
        raw2 = backup.pack(self.payload(48000))
        second = cloud.save({'bucket':'test'},self.owner,raw2,self.ref(raw2))
        self.assertLess(sum(n for key,n in FakeS3.puts), 20000)
        self.assertGreater(first_bytes, 7000000)
        with tempfile.TemporaryDirectory() as folder, patch.object(backup,'ROOT',Path(folder)):
            payload = cloud.restore({'bucket':'test'},self.owner,dict(second,id='dk'))
            self.assertEqual(payload['checkpoint']['values']['salary'],48000)
            np.testing.assert_array_equal(payload['checkpoint']['values']['outcomes'],self.payload()['checkpoint']['values']['outcomes'])
    def test_tampered_index_and_segment_are_rejected(self):
        raw = backup.pack(self.payload())
        ref = cloud.save({'bucket':'test'},self.owner,raw,self.ref(raw))
        key = f'simmah-inputs/{self.owner}/{ref["cloud_key"]}'
        original = FakeS3.objects[key];FakeS3.objects[key] = b'bad'
        with self.assertRaisesRegex(ValueError,'index failed'):
            cloud.restore({},self.owner,ref)
        FakeS3.objects[key] = original
        part = next(k for k in FakeS3.objects if '/parts/' in k)
        FakeS3.objects[part] = b'bad'
        with self.assertRaisesRegex(ValueError,'segment failed'):
            cloud.restore({},self.owner,ref)
    def test_server_wipe_recovers_from_cloud_without_browser_upload(self):
        payload = self.payload()
        raw = backup.pack(payload)
        ref = cloud.save({},self.owner,raw,self.ref(raw))
        row = {**ref,'name':'entries.csv','open':True}
        state = {persistence.KEY:dict(event='boot',boot=dict(owner=self.owner,records=[row],active='dk'))}
        app = SimpleNamespace(spinner=lambda *_a,**_k:nullcontext(),session_state=state,secrets={'input_archive':{'bucket':'test'}})
        with tempfile.TemporaryDirectory() as folder, patch.object(backup,'ROOT',Path(folder)):
            persistence.begin(app)
            self.assertTrue(state['_slate_cloud_restored'])
            self.assertNotIn('_slate_backup_restore',state)
            self.assertEqual(state['_slate_pending']['_session_checkpoint']['values']['salary'],49000)
    def test_cloud_failure_keeps_browser_backup_available(self):
        with tempfile.TemporaryDirectory() as folder, patch.multiple(backup,ROOT=Path(folder)/'cache',STAGING=Path(folder)/'static'), patch.object(cloud,'save',side_effect=RuntimeError('denied')):
            ref = persistence.save_job(self.owner,self.payload(),None,1,{'bucket':'test'})
            self.assertFalse(ref.get('cloud_ok'))
            self.assertIn('cloud_error',ref)
            self.assertTrue(backup.path_for(self.owner,ref['token'],backup.STAGING).exists())
    def test_probe_verifies_real_readback_contract(self):
        self.assertTrue(cloud.probe({'bucket':'test'},self.owner))
        with patch.object(FakeS3,'get',return_value=b'wrong'):
            with self.assertRaises(ValueError):cloud.probe({},self.owner)

    def test_existing_browser_checkpoint_is_promoted_once(self):
        from simmah_session_workspaces import checkpoint
        row = self.payload()['record']
        state = {'_slate_active':row,'_slate_records':{'dk':row},
                 '_slate_backup_owner':self.owner,'_slate_cloud_config':{'bucket':'test'},'salary':49000}
        app = SimpleNamespace(session_state=state)
        row['_session_checkpoint'] = checkpoint(app)
        state['_slate_backup_captured'] = {'dk':row['_session_checkpoint']}
        state['_slate_backup_refs'] = {'dk':{'digest':'old','revision':1,'token':'b'*32}}
        with patch.object(persistence,'advance'):
            persistence.schedule(app)
            self.assertIn('dk',state['_slate_backup_queue'])
            state['_slate_backup_queue'].clear()
            state['_slate_backup_refs']['dk']['cloud_ok'] = True
            persistence.schedule(app)
            self.assertFalse(state['_slate_backup_queue'])
