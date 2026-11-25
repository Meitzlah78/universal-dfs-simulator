import ast
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import pandas as pd
from simmah_nba_auto_swap import render_auto_swap,refresh_pool,input_signature
from simmah_nba_frame import data_view
from simmah_nba_late_swap import locked_players
from simmah_nba_player_display import display_pool
from simmah_export_history import render_history

class Rerun(BaseException):pass
class Evidence(dict):
    def __deepcopy__(self,memo):raise AssertionError('Read-only clock/display check copied provider payload')

class IdleTests(unittest.TestCase):
    def pool(self):
        p=pd.DataFrame({'Player ID':['1','2'],'Name':['A','B'],'Team':['NY','PHI'],'Opponent':['PHI','NY'],
            'Projection':[10.,20.],'Game Start':['2020-01-01T19:00:00-05:00','2099-01-01T19:00:00-05:00'],
            'Injury Status':['Active','Active'],'Expected Starter':[False,False],
            'Starter Confirmed':[False,False]})
        p.attrs.update(platform='DraftKings',slate_date='2026-11-18');return p

    def test_all_locked_never_fetches_or_installs_auto_swap_timer(self):
        p=self.pool();p['Game Start']='2020-01-01T19:00:00-05:00'
        app=SimpleNamespace(info=lambda message:None)
        with patch('simmah_nba_auto_swap.refresh_pool',side_effect=AssertionError('provider fetched')):
            render_auto_swap(app,p,b'', '1',48000,25,[],None,None,False,None,False)

    def test_partial_lock_fetches_and_updates_only_unstarted_players(self):
        p=self.pool();seen=[]
        def fetch(*args,**kwargs):
            seen.append(True)
            return {('a','NY'):99.,('b','PHI'):30.},{('b','PHI'):{'RotoWire Injury':'Active'}},'1'
        out=refresh_pool(p,fetch)
        self.assertEqual(len(seen),1)
        self.assertEqual(out.Projection.tolist(),[10.,30.])
        self.assertEqual(p.Projection.tolist(),[10.,20.])

    def test_clock_and_display_reads_do_not_copy_raw_payload(self):
        p=self.pool();p.attrs['raw']=Evidence(payload=list(range(10000)))
        original=data_view(p).copy();evidence=p.attrs['raw'];payload=list(evidence['payload'])
        self.assertEqual(locked_players(p).tolist(),[True,False])
        input_signature(p,locked_players(p))
        shown=display_pool(p)
        self.assertEqual(shown.Name.tolist(),['A','B'])
        shown.loc[0,'Name']='Changed display only'
        shown.loc[0,'Projection']=0.
        pd.testing.assert_frame_equal(data_view(p),original)
        self.assertIs(p.attrs['raw'],evidence)
        self.assertEqual(evidence['payload'],payload)

    def test_idle_history_never_installs_a_timer_or_component(self):
        app=SimpleNamespace(session_state={})
        with patch('simmah_export_history.finish_exports',return_value=False),patch('simmah_export_history._render_history') as draw,patch('streamlit.components.v1.declare_component',side_effect=AssertionError('idle poll')):
            render_history(app,{'format':'DraftKings','contest_id':'1'},'x')
        draw.assert_called_once()

    def test_completed_export_requests_one_refresh_without_manual_click(self):
        calls=[]
        def rerun(**kwargs):calls.append(kwargs);raise Rerun()
        app=SimpleNamespace(session_state={},rerun=rerun)
        with patch('simmah_export_history.finish_exports',return_value=True),patch('simmah_workspace_persistence.schedule') as save:
            with self.assertRaises(Rerun):render_history(app,{'format':'DK','contest_id':'1'},'x')
        self.assertEqual(calls,[{'scope':'app'}]);save.assert_called_once_with(app)

    def test_download_and_history_share_same_fragment(self):
        from simmah_slate_workspaces import workspace_download_button

        active = []
        seen = []

        def fragment(fn):
            def run():
                active.append(fn)
                try:
                    return fn()
                finally:
                    active.pop()
            return run

        app = SimpleNamespace(session_state={}, fragment=fragment)
        with patch('simmah_export_history.audited_download', side_effect=lambda *a, **k: seen.append(active[-1])), patch(
            'simmah_export_history.render_history', side_effect=lambda *a: seen.append(active[-1])
        ):
            workspace_download_button(app, 'Export', b'csv', 'entries.csv', export_checkpoint={'format': 'DK'})
        self.assertEqual(len(seen), 2)
        self.assertIs(seen[0], seen[1])

    def test_calibration_completion_stops_timer_and_new_job_rearms(self):
        tree=ast.parse(Path('simmah_archive_ui.py').read_text())
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='running_status')
        timers=[];messages=[]
        def rerun(**kwargs):raise Rerun()
        app=SimpleNamespace(fragment=lambda **kw:lambda f:timers.append(kw) or f,rerun=rerun,caption=messages.append)
        for state in ['verified_convergence','failed','running','queued']:
            env={'st':app,'archive':SimpleNamespace(jobs=lambda state=state:[{'state':state}])}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'calibration','exec'),env)
            if state in ['failed','verified_convergence']:
                with self.assertRaises(Rerun):env['running_status']()
            else:env['running_status']()
        self.assertEqual(messages,['Calibration: running','Calibration: queued'])
        self.assertTrue(all(t=={'run_every':'5s'} for t in timers))
