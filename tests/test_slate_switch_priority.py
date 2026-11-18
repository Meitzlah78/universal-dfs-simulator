"""Route navigation before old-slate work, keeping complete detached builds."""
import contextlib
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import numpy as np
import pandas as pd
import simmah_slate_workspaces as workspaces
from simmah_session_workspaces import restore_checkpoint


class SlateSwitchPriorityTests(unittest.TestCase):
    def app(self):
        dk={'id':'dk','name':'DK.csv','data':'ZGstY3N2'}
        fd={'id':'fd','name':'FD.csv','data':'ZmQtY3N2',
            '_session_checkpoint':{'values':{'dfs_format':'FanDuel NBA','portfolio':pd.DataFrame({'Player':['FD saved']})},'uploads':{},'artifacts':{}}}
        state={'_slate_fresh_mode':True,'_slate_active':dk,'_slate_records':{'dk':dk,'fd':fd},
            '_slate_session_tabs':{'event':'switch-now','selected_id':'fd'},
            'dfs_format':'DraftKings NBA','portfolio':pd.DataFrame({'Player':['DK saved']}),
            'outcomes':np.arange(40000).reshape(10000,4),'minimum_salary':48000}
        return SimpleNamespace(session_state=state,container=lambda:contextlib.nullcontext(),warning=lambda m:self.fail(m),rerun=lambda:self.fail('Unnecessary extra rerun'))

    def begin(self,app,**kwargs):
        with patch('simmah_workspace_persistence.begin',**kwargs),patch('simmah_saved_cleanup.render_cleanup'):
            workspaces.begin_workspaces(app)

    def test_switch_consumed_before_persistence_and_old_slate_models(self):
        app=self.app();state=app.session_state
        def begin_backup(st):
            self.assertEqual(state['_slate_pending']['id'],'fd')
            self.assertIn('_session_checkpoint',state['_slate_records']['dk'])
        with patch('simmah_session_workspaces.fingerprint',side_effect=AssertionError('Must not scan old autosave first')):
            self.begin(app,side_effect=begin_backup)
        self.assertEqual(state['_slate_active']['id'],'fd')
        self.assertEqual(state['portfolio'].Player.tolist(),['FD saved'])
        self.assertEqual(state['dfs_format'],'FanDuel NBA')
        self.assertNotIn('outcomes',state)
        timing=state['_slate_last_switch_metrics']
        self.assertTrue(timing['destination_in_memory'])
        for key in ['capture_seconds','backup_recovery_seconds','workspace_restore_seconds','routing_seconds']:self.assertGreaterEqual(timing[key],0)
        saved=state['_slate_records']['dk']['_session_checkpoint']
        self.assertEqual(saved['values']['minimum_salary'],48000)
        self.assertEqual(saved['values']['portfolio'].Player.tolist(),['DK saved'])
        np.testing.assert_array_equal(saved['values']['outcomes'],np.arange(40000).reshape(10000,4))

    def test_switch_captures_latest_edits_and_round_trip_stays_isolated(self):
        app=self.app();state=app.session_state
        original=state['outcomes'];state['minimum_salary']=49000
        self.begin(app)
        saved=state['_slate_records']['dk']['_session_checkpoint']
        original[0,0]=-1
        self.assertEqual(saved['values']['outcomes'][0,0],0)
        state['portfolio'].iloc[0,0]='FD edited'
        state['_slate_session_tabs']={'event':'back-to-dk','selected_id':'dk'}
        self.begin(app)
        self.assertEqual(state['minimum_salary'],49000)
        self.assertEqual(state['portfolio'].Player.tolist(),['DK saved'])
        fd=state['_slate_records']['fd']['_session_checkpoint']
        self.assertEqual(fd['values']['portfolio'].Player.tolist(),['FD edited'])
        restore_checkpoint(app,fd)
        self.assertEqual(state['portfolio'].Player.tolist(),['FD edited'])

    def test_same_event_is_not_replayed(self):
        app=self.app();self.begin(app)
        with patch('simmah_session_workspaces.checkpoint',side_effect=AssertionError('Repeated capture')):
            self.begin(app)
        self.assertEqual(app.session_state['_slate_active']['id'],'fd')

    def test_close_active_routes_before_persistence(self):
        app=self.app();app.session_state['_slate_session_tabs']={'event':'close-dk','closed_id':'dk'}
        self.begin(app)
        self.assertEqual(app.session_state['_slate_active']['id'],'fd')
        self.assertNotIn('dk',app.session_state['_slate_records'])

    def test_close_last_clears_active_before_old_page_draws(self):
        app=self.app();state=app.session_state;state['_slate_records'].pop('fd')
        state['_slate_session_tabs']={'event':'close-last','closed_id':'dk'}
        self.begin(app)
        self.assertNotIn('_slate_active',state)
        self.assertNotIn('portfolio',state)
        self.assertFalse(state['_slate_records'])

    def test_invalid_event_never_captures_or_changes_current_slate(self):
        app=self.app();state=app.session_state
        state['_slate_session_tabs']={'event':'invalid','selected_id':'not-a-slate'}
        with patch('simmah_session_workspaces.checkpoint',side_effect=AssertionError('Unexpected capture')):
            self.begin(app)
        self.assertEqual(state['_slate_active']['id'],'dk')
        self.assertEqual(state['portfolio'].Player.tolist(),['DK saved'])

    def test_early_capture_queues_inactive_dk_for_durable_save(self):
        from simmah_workspace_persistence import schedule
        app=self.app();state=app.session_state;state['_slate_backup_owner']='a'*32
        self.begin(app)
        with patch('simmah_workspace_persistence.advance'):schedule(app)
        queue=state['_slate_backup_queue']
        self.assertEqual(set(queue),{'dk','fd'})
        self.assertEqual(queue['dk'][0]['checkpoint']['values']['minimum_salary'],48000)
        self.assertEqual(queue['dk'][0]['checkpoint']['values']['portfolio'].Player.tolist(),['DK saved'])
        self.assertEqual(queue['fd'][0]['checkpoint']['values']['portfolio'].Player.tolist(),['FD saved'])

    def test_switch_timing_display_is_optional_and_reports_stages(self):
        from simmah_workspace_persistence import render_switch_metrics
        captions=[];app=SimpleNamespace(session_state={},caption=captions.append)
        render_switch_metrics(app);self.assertFalse(captions)
        app.session_state['_slate_last_switch_metrics']={'routing_seconds':.12,'capture_seconds':.04,'backup_recovery_seconds':.05,'workspace_restore_seconds':.03}
        render_switch_metrics(app)
        self.assertIn('0.12s',captions[0]);self.assertIn('0.04s',captions[0]);self.assertIn('0.05s',captions[0]);self.assertIn('0.03s',captions[0])
