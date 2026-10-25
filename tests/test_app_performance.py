"""Verify eliminated work as well as the data that must survive it."""
import ast
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import streamlit as st

from simmah_session_workspaces import checkpoint, restore_checkpoint

APP = Path(__file__).resolve().parents[1] / 'dfs_app.py'


def function(name, env, decorated=False):
    tree = ast.parse(APP.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    if not decorated:
        node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP), 'exec'), env)
    return env[name]


class PerformanceTest(unittest.TestCase):
    def test_fd_failure_cached_across_reruns_and_scoped_to_contest(self):
        lookup = function('fetch_fanduel_contest_details', {'st': st, 'requests': requests}, True)
        lookup.clear()
        with patch.object(requests, 'get', side_effect=requests.Timeout('unavailable')) as get:
            for _ in range(5): self.assertIsNone(lookup('111-222'))
            self.assertEqual(get.call_count, 3)
            lookup('111-333')
            self.assertEqual(get.call_count, 6)
        lookup.clear()

    def test_optional_feed_failures_are_cached_until_retry(self):
        for name, module, call, expected in [
            ('download_rotowire_projections', 'simmah_rotowire.download',
             ('DraftKings Classic', ('NYJ', 'NE'), ('2026-10-25',)), ({}, None)),
            ('automatic_game_lines_cached', 'simmah_auto_game_lines.download_lines',
             (('NYJ @ NE',), ('2026-10-25',)), {}),
        ]:
            with self.subTest(name=name):
                lookup = function(name, {'st': st}, True)
                lookup.clear()
                with patch(module, side_effect=TimeoutError('offline')) as download:
                    for _ in range(5): self.assertEqual(lookup(*call), expected)
                    self.assertEqual(download.call_count, 1)
                    lookup.clear()
                    lookup(*call)
                    self.assertEqual(download.call_count, 2)
                lookup.clear()

    def test_no_background_projection_download_before_slate_is_parsed(self):
        calls=[]
        state={}
        refresh=function('refresh_public_projection_sources', {
            'st':SimpleNamespace(session_state=state),
            'download_public_projection_table':lambda *a,**kw:calls.append((a,kw)) or {}})
        self.assertEqual(refresh(('DraftKings Classic',)), {})
        self.assertEqual(calls, [])
        state['projection_refresh_targets']={'DraftKings Classic':dict(names=['Player'],teams=('NYJ',),uploaded={'DFF':{'player':20}})}
        status=refresh(('DraftKings Classic',))
        self.assertTrue(status['DFF (DraftKings Classic)'])
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1],dict(target_names=['Player'],target_teams=('NYJ',)))

    def test_unchanged_snapshot_does_not_rewrite_files_or_change_saved_time(self):
        class Clock:
            current=datetime(2026,10,25,12,tzinfo=ZoneInfo('America/New_York'))
            @classmethod
            def now(cls, tz): return cls.current.astimezone(tz)
        with tempfile.TemporaryDirectory() as tmp:
            state={'selected_dk_contest':{'id':'123','name':'Dime','entry_fee':.1}}
            env={'pd':pd,'np':np,'st':SimpleNamespace(session_state=state),'ZoneInfo':ZoneInfo,
                 '_safe_snapshot_slug':lambda v:'dk','_pregame_snapshot_dir':lambda:Path(tmp)}
            save=function('save_automatic_pregame_snapshot',env)
            frame=pd.DataFrame({'Name':['Player'],'Team':['NYJ'],'Salary':[5000],'Projection':[20.]})
            with patch('datetime.datetime',Clock):
                path=save(frame,'DraftKings Classic')
                before=path.read_bytes();modified=path.stat().st_mtime_ns
                Clock.current+=timedelta(seconds=10)
                save(frame,'DraftKings Classic')
                self.assertEqual(path.read_bytes(),before)
                self.assertEqual(path.stat().st_mtime_ns,modified)
                frame.loc[0,'Projection']=21.
                save(frame,'DraftKings Classic')
                self.assertNotEqual(path.read_bytes(),before)

    def test_full_simulations_survive_tab_switch_and_are_isolated(self):
        # Larger than the browser snapshot's 16 MiB cache limit.
        outcomes=pd.DataFrame(np.arange(2200000,dtype=float).reshape(10000,220))
        state={'outcomes':outcomes,'build':{'controls':[10,20]},'dfs_format':'DraftKings Classic',
               '_slate_action_keys':{'run'},'run':True,'test_api_key':'private'}
        app=SimpleNamespace(session_state=state)
        saved=checkpoint(app)
        state['outcomes'].iat[0,0]=-1
        state['build']['controls'][0]=99
        restore_checkpoint(app,saved)
        self.assertEqual(state['outcomes'].shape,(10000,220))
        self.assertEqual(state['outcomes'].iat[0,0],0)
        self.assertEqual(state['build']['controls'],[10,20])
        self.assertNotIn('run',state)
        self.assertNotIn('test_api_key',state)

    def test_upload_switch_keeps_independent_settings_and_complete_builds(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('''
import streamlit as st
from unittest.mock import patch
import numpy as np
from simmah_slate_workspaces import select_upload, StoredUpload
st.session_state['_slate_fresh_mode']=True
for site in ('DK','FD'):
    if st.button('Load '+site, key='load_'+site):
        raw=('Entry ID,Contest Name,Contest ID,Entry Fee,DST\\n'+('1' if site=='DK' else '2')+',Contest,123,.10,\\n').encode()
        with patch('simmah_archive_ui.capture_upload'):
            select_upload(st,StoredUpload(raw,site+'.csv'))
st.number_input('Salary', min_value=0, max_value=60000, value=0, key='salary')
if st.button('Build',key='run_build'):
    st.session_state['outcomes']=np.ones((10000,220))
st.write(str(st.session_state.get('_slate_active',{}).get('name','none')))
''').run()
        app.button(key='load_DK').click().run()
        app.number_input(key='salary').set_value(48000).run()
        app.button(key='run_build').click().run()
        app.button(key='load_FD').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key='salary').value,0)
        app.number_input(key='salary').set_value(58000).run()
        app.button(key='load_DK').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key='salary').value,48000)
        self.assertEqual(app.session_state['outcomes'].shape,(10000,220))
        app.button(key='load_FD').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key='salary').value,58000)
        self.assertNotIn('outcomes',app.session_state)
