import io,json,unittest,zipfile,hashlib,tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import pandas as pd
from simmah_export_history import capture_export,latest_record,latest_player_snapshot,HISTORY
from simmah_slate_workspaces import snapshot,restore

class ExportHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        from simmah_export_history import persist_checkpoint
        self.patch=patch('simmah_export_history.persist_checkpoint',side_effect=lambda record,folder:persist_checkpoint(record,Path(self.temp.name)))
        self.patch.start();self.addCleanup(self.patch.stop)
        self.errors=[]
        self.st=SimpleNamespace(session_state={'candidates':pd.DataFrame({'Captain':['A']}),'evaluation':np.arange(12).reshape(3,4),'scenario_control':100},toast=lambda x:None,error=self.errors.append)
        self.context={'format':'DraftKings Showdown','contest_id':'123','slate_id':'s', 'kind':'entries',
            'player_pool':pd.DataFrame({'Name':['A'],'Projection':[12.]}),'snapshot_metadata':{'payout_schedule':[1,0]}}
    def save(self,data=b'Entry ID,CPT\r\n1,2\r\n',context=None):
        capture_export(self.st,data,'entries.csv',context or self.context)
        self.assertFalse(self.errors)
        return self.st.session_state[HISTORY][-1]
    def test_every_click_retained_even_identical_csv(self):
        a=self.save();b=self.save()
        self.assertNotEqual(a['export_id'],b['export_id']);self.assertEqual(len(self.st.session_state[HISTORY]),2)
        self.assertEqual(latest_record(self.st.session_state,'DraftKings Showdown','123')['export_id'],b['export_id'])
        with zipfile.ZipFile(io.BytesIO(a['archive'])) as archive:
            self.assertEqual(archive.read('export.csv'),b'Entry ID,CPT\r\n1,2\r\n')
            for name,digest in json.loads(archive.read('hashes.json')).items():self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)
    def test_reports_and_foreign_contests_never_override_latest(self):
        first=self.save();self.save(context={**self.context,'kind':'report'})
        self.save(context={**self.context,'contest_id':'456'})
        self.assertEqual(latest_record(self.st.session_state,'DraftKings Showdown','123')['export_id'],first['export_id'])
        self.assertIsNone(latest_record(self.st.session_state,'FanDuel Single Game','123'))
    def test_late_swap_retains_before_after_and_is_latest(self):
        parent=self.save();context={**self.context,'kind':'late_swap','late_swap':{'before':['1'],'after':['2'],'lock_mask':[True,False]}}
        child=self.save(b'swapped',context)
        self.assertEqual(child['parent_export_id'],parent['export_id'])
        self.assertEqual(latest_record(self.st.session_state,'DraftKings Showdown','123')['kind'],'late_swap')
        with zipfile.ZipFile(io.BytesIO(child['archive'])) as z:self.assertIn('late_swap.json',z.namelist())
    def test_history_survives_workspace_roundtrip_and_state_is_not_recursive(self):
        first=self.save();second=self.save();loaded={};restore(loaded,snapshot(self.st.session_state))
        self.assertEqual(len(loaded[HISTORY]),2)
        self.assertEqual(loaded[HISTORY][0]['archive'],first['archive'])
        with zipfile.ZipFile(io.BytesIO(second['archive'])) as z:
            state={};restore(state,z.read('workspace_snapshot.txt').decode())
            self.assertNotIn(HISTORY,state)
            np.testing.assert_array_equal(state['evaluation'],self.st.session_state['evaluation'])
            self.assertEqual(state['scenario_control'],100)
        frame,meta=latest_player_snapshot(loaded,'DraftKings Showdown','123')
        self.assertEqual(frame.Projection.iloc[0],12)
        self.assertEqual(meta['payout_schedule'],[1,0])
    def test_server_archive_is_exclusive(self):
        from simmah_export_history import persist_checkpoint
        record=self.save();original=(Path(self.temp.name)/(record['export_id']+'.zip')).read_bytes()
        with self.assertRaises(FileExistsError):persist_checkpoint(record,self.temp.name)
        self.assertEqual((Path(self.temp.name)/(record['export_id']+'.zip')).read_bytes(),original)

    def test_download_wrapper_binds_capture_and_preserves_callback(self):
        import ast
        from unittest.mock import patch
        tree=ast.parse(Path('simmah_slate_workspaces.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='workspace_download_button')
        env={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'wrapper','exec'),env)
        bound={}
        def download(*args,**kwargs):bound.update(kwargs);return False
        self.st.download_button=download
        calls=[]
        with patch('simmah_export_history.render_history'):
            env[fn.name](self.st,'EXPORT',b'exact','entries.csv',export_checkpoint=self.context,
                on_click=lambda x:calls.append(x),args=(4,))
        self.assertNotIn('export_checkpoint',bound)
        bound['on_click'](*bound['args'])
        self.assertEqual(calls,[4]);self.assertEqual(len(self.st.session_state[HISTORY]),1)

    def test_existing_callback_preserved(self):
        called=[];capture_export(self.st,b'csv','entries.csv',self.context,lambda x:called.append(x),(3,),{})
        self.assertEqual(called,[3]);self.assertEqual(len(self.st.session_state[HISTORY]),1)

if __name__=='__main__':unittest.main()
