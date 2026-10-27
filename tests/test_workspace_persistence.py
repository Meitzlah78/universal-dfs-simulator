import base64
import contextlib
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

import simmah_workspace_backup as backup
import simmah_workspace_persistence as persistence
from simmah_session_workspaces import restore_checkpoint


class Stop(Exception): pass


class PersistenceTest(unittest.TestCase):
    def app(self,state):
        return SimpleNamespace(session_state=state,stop=lambda:(_ for _ in ()).throw(Stop()),error=lambda text:None,button=lambda *a,**k:False)

    def payload(self,ident='dk'):
        return dict(record=dict(id=ident,name=ident+'.csv',data=base64.b64encode(b'original csv').decode()),
            checkpoint=dict(values=dict(salary=49000,portfolio=pd.DataFrame({'Player':['A','B'],'Score':[123.4,125.6]}),
                outcomes=np.arange(2200000,dtype=float).reshape(10000,220)),uploads={},artifacts={'package':{'raw':b'calibration package'}}))

    def test_new_session_recovers_both_slates_without_loading_inactive_build(self):
        with tempfile.TemporaryDirectory() as folder,patch.multiple(backup,ROOT=Path(folder)/'cache',STAGING=Path(folder)/'static'):
            refs={sid:{**backup.write_backup('a'*32,backup.pack(self.payload(sid))), 'id':sid,'name':sid+'.csv','open':True,'revision':1} for sid in ('dk','fd')}
            state={persistence.KEY:dict(event='boot',boot=dict(owner='a'*32,records=list(refs.values()),active='dk'))}
            st=self.app(state);persistence.begin(st)
            self.assertEqual(state['_slate_pending']['id'],'dk')
            self.assertNotIn('_session_checkpoint',state['_slate_records']['fd'])
            restore_checkpoint(st,state['_slate_pending']['_session_checkpoint'])
            self.assertEqual(state['salary'],49000)
            self.assertEqual(state['outcomes'].shape,(10000,220))
            self.assertEqual(state['_slate_archive_pending']['package']['raw'],b'calibration package')
            state['_slate_pending']=state['_slate_records']['fd'];persistence.begin(st)
            self.assertEqual(state['_slate_pending']['id'],'fd')

    def test_host_disk_wipe_recovers_verified_chunks_before_restoring_widgets(self):
        raw=backup.pack(self.payload());ref=dict(token='b'*32,digest=backup.digest(raw),bytes=len(raw),id='dk',name='dk.csv',open=True,revision=1)
        with tempfile.TemporaryDirectory() as folder,patch.multiple(backup,ROOT=Path(folder)/'cache',STAGING=Path(folder)/'static'),patch.object(persistence,'component',return_value=lambda **kw:None):
            state={persistence.KEY:dict(event='boot',boot=dict(owner='a'*32,records=[ref],active='dk'))};st=self.app(state)
            with self.assertRaises(Stop):persistence.begin(st)
            self.assertNotIn('outcomes',state)
            self.assertEqual(state['_slate_backup_restore']['digest'],ref['digest'])
            text=json.dumps(dict(selected=dict(id='dk',data=base64.b64encode(raw).decode())))
            parts=[text[i:i+1000000] for i in range(0,len(text),1000000)]
            for i,part in enumerate(parts):
                state[persistence.KEY]=dict(event=str(i),upload_part=dict(id='restore',index=i,total=len(parts),data=part))
                if i<len(parts)-1:
                    with self.assertRaises(Stop):persistence.begin(st)
                    self.assertNotIn('outcomes',state)
                else:persistence.begin(st)
            restore_checkpoint(st,state['_slate_pending']['_session_checkpoint'])
            np.testing.assert_array_equal(state['outcomes'],self.payload()['checkpoint']['values']['outcomes'])
            self.assertNotIn('_slate_backup_restore',state)
            self.assertEqual(backup.load_backup('a'*32,ref)['record']['id'],'dk')

    def test_unacknowledged_save_never_deletes_previous_confirmed_backup(self):
        with tempfile.TemporaryDirectory() as folder,patch.multiple(backup,ROOT=Path(folder)/'cache',STAGING=Path(folder)/'static'):
            first=backup.write_backup('a'*32,backup.pack(self.payload()));first['revision']=1
            future=Future();second={**backup.write_backup('a'*32,backup.pack(self.payload('new'))),'revision':2};future.set_result(second)
            state={'_slate_backup_owner':'a'*32,'_slate_backup_refs':{'dk':first},'_slate_backup_confirmed':{'dk':first},'_slate_backup_future':future,'_slate_backup_saving':'dk'}
            persistence.advance(state)
            self.assertTrue(backup.path_for('a'*32,first['token']).exists())
            state[persistence.KEY]=dict(event='ack',saved={'dk':second});persistence.consume(self.app(state))
            self.assertFalse(backup.path_for('a'*32,first['token']).exists())
            self.assertTrue(backup.path_for('a'*32,second['token']).exists())
            self.assertFalse(backup.path_for('a'*32,second['token'],backup.STAGING).exists())

    def test_unchanged_payload_reuses_backup_without_disk_growth(self):
        with tempfile.TemporaryDirectory() as folder,patch.multiple(backup,ROOT=Path(folder)/'cache',STAGING=Path(folder)/'static'):
            payload=self.payload();first=persistence.save_job('a'*32,payload,None,1)
            second=persistence.save_job('a'*32,payload,first,2)
            self.assertEqual(first['token'],second['token']);self.assertEqual(second['revision'],2)

    def test_status_arguments_never_contain_originals_or_arrays(self):
        state={'_slate_generation':'g','_slate_backup_booted':True,'_slate_backup_owner':'a'*32,'_slate_records':{'dk':{**self.payload()['record'],'_session_checkpoint':self.payload()['checkpoint']}}}
        args=persistence.args_for(state)
        self.assertLess(len(json.dumps(args)),1000)
        self.assertNotIn('outcomes',json.dumps(args));self.assertNotIn('data',args['records'][0])

    def test_binary_recovery_spools_over_256_parts_and_restores_only_after_verification(self):
        raw=backup.pack(self.payload())
        chunk=max(1,len(raw)//270)
        ref=dict(token='b'*32,digest=backup.digest(raw),bytes=len(raw),id='dk')
        state={'_slate_backup_owner':'a'*32,'_slate_backup_restore':ref}
        with tempfile.TemporaryDirectory() as folder,patch.multiple(backup,ROOT=Path(folder)/'cache'),patch.object(persistence,'RECOVERY_CHUNK_BYTES',chunk):
            parts=[raw[i:i+chunk] for i in range(0,len(raw),chunk)]
            self.assertGreater(len(parts),256)
            for i,data in enumerate(parts):
                packet=dict(id='binary',index=i,total=len(parts),data=base64.b64encode(data).decode())
                persistence.receive_backup_part(state,packet)
                if i<len(parts)-1:
                    self.assertNotIn('_slate_pending',state)
                    self.assertFalse(backup.path_for('a'*32,ref['token']).exists())
                    self.assertNotIn('parts',state['_slate_backup_transfer'])
                    persistence.receive_backup_part(state,packet)  # Duplicate ACK retry is idempotent.
            persistence.receive_backup_part(state,packet)  # Late final frame is harmless.
            self.assertEqual(state['_slate_pending']['id'],'dk')
            np.testing.assert_array_equal(state['_slate_pending']['_session_checkpoint']['values']['outcomes'],self.payload()['checkpoint']['values']['outcomes'])
            self.assertEqual(backup.path_for('a'*32,ref['token']).read_bytes(),raw)

    def test_binary_recovery_rejects_corruption_and_order_without_replacing_backup(self):
        raw=backup.pack(dict(record=dict(id='dk'),checkpoint=dict(values=dict(salary=49000))))
        ref=dict(token='b'*32,digest='0'*64,bytes=len(raw),id='dk')
        state={'_slate_backup_owner':'a'*32,'_slate_backup_restore':ref}
        with tempfile.TemporaryDirectory() as folder,patch.object(backup,'ROOT',Path(folder)),patch.object(persistence,'RECOVERY_CHUNK_BYTES',len(raw)):
            path=backup.path_for('a'*32,ref['token']);path.parent.mkdir(parents=True);path.write_bytes(b'previous')
            with self.assertRaisesRegex(ValueError,'verification'):
                persistence.receive_backup_part(state,dict(id='binary',index=0,total=1,data=base64.b64encode(raw).decode()))
            self.assertEqual(path.read_bytes(),b'previous')
            self.assertNotIn('_slate_pending',state)
            with patch.object(persistence,'RECOVERY_CHUNK_BYTES',1):
                with self.assertRaisesRegex(ValueError,'out of order'):
                    persistence.receive_backup_part(state,dict(id='binary',index=1,total=len(raw),data=base64.b64encode(raw[1:2]).decode()))
        state={'_slate_backup_restore':dict(ref,bytes=backup.MAX_BYTES+1)}
        with self.assertRaisesRegex(ValueError,'reference'):
            persistence.receive_backup_part(state,dict(id='bad',index=0,total=1,data=''))
