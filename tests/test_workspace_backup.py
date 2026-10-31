from datetime import datetime
import io
import tempfile
import unittest
import zipfile
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from simmah_workspace_backup import pack, unpack, write_backup, load_backup
from simmah_slate_workspaces import StoredUpload

class WorkspaceBackupTest(unittest.TestCase):
    def payload(self):
        frame=pd.DataFrame({'Player':['A','B'],'Eligible':[{'QB'},{'WR','TE'}], 'Salary':pd.Series([5000,None],dtype='Int64'),'Lock':pd.Series([True,pd.NA],dtype='boolean')})
        frame.attrs={'team':'NYJ','data':np.array([1,2])}
        return {'record':{'id':'slate','name':'DKEntries.csv','data':'original'},'checkpoint':{'values':{'frame':frame,'outcomes':np.arange(2200000,dtype=float).reshape(10000,220),'time':datetime(2026,10,25,19,tzinfo=ZoneInfo('America/New_York')),'mapping':{('a',2):{3,4}},'secret_password':'never'},'uploads':{'projection':StoredUpload(b'Name,Projection\nA,20','projection.csv')}}}
    def test_full_build_and_inputs_survive_memory_loss(self):
        original=self.payload();raw=pack(original);result=unpack(raw)
        pd.testing.assert_frame_equal(result['checkpoint']['values']['frame'],original['checkpoint']['values']['frame'])
        np.testing.assert_array_equal(result['checkpoint']['values']['outcomes'],original['checkpoint']['values']['outcomes'])
        self.assertEqual(result['checkpoint']['values']['time'],original['checkpoint']['values']['time'])
        self.assertEqual(result['checkpoint']['values']['mapping'],{('a',2):{3,4}})
        self.assertNotIn('secret_password',result['checkpoint']['values'])
        self.assertEqual(result['checkpoint']['uploads']['projection'].getvalue(),b'Name,Projection\nA,20')
    def test_snapshot_bytes_are_deterministic(self):
        payload=self.payload();self.assertEqual(pack(payload),pack(payload))
    def test_server_reboot_and_browser_reupload_recover(self):
        raw=pack(self.payload())
        with tempfile.TemporaryDirectory() as root:
            ref=write_backup('a'*32,raw,root)
            self.assertEqual(load_backup('a'*32,ref,root)['record']['id'],'slate')
            # Host disk wiped: the exact browser copy can recreate the private file.
            from pathlib import Path
            for path in Path(root).rglob('*.zip'):path.unlink()
            with self.assertRaises(FileNotFoundError):load_backup('a'*32,ref,root)
            write_backup('a'*32,raw,root,token=ref['token'])
            self.assertEqual(load_backup('a'*32,ref,root)['checkpoint']['values']['outcomes'].shape,(10000,220))
    def test_tampering_and_invalid_private_paths_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            raw=pack(self.payload());ref=write_backup('a'*32,raw,root)
            ref['digest']='0'*64
            with self.assertRaises(ValueError):load_backup('a'*32,ref,root)
            with self.assertRaises(ValueError):write_backup('../other',raw,root)

    def test_corrupt_zip_and_forged_array_dimensions_fail_before_allocation(self):
        from simmah_workspace_backup import digest
        with self.assertRaises(ValueError):unpack(b'not a workspace zip')
        # Safe JSON object-array codec checks the declared product before allocation.
        import json
        malicious={'t':'objects','shape':[10**15],'values':[]}
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as bundle:
            bundle.writestr('manifest.json',json.dumps({'schema':1,'payload':malicious}))
        with self.assertRaises(ValueError):unpack(out.getvalue())
