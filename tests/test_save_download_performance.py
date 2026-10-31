"""Unchanged saves do no work; audit exports freeze values without blocking."""
import io
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import simmah_export_history as exports
import simmah_workspace_persistence as persistence
from simmah_session_workspaces import checkpoint, fingerprint
from simmah_slate_workspaces import restore


class SaveDownloadPerformanceTests(unittest.TestCase):
    def app(self):
        row = dict(id='dk', name='entries.csv', data='original')
        state = {'_slate_active':row, '_slate_records':{'dk':row},
                 '_slate_backup_owner':'a'*32, 'salary':49000,
                 'outcomes':np.arange(24).reshape(6,4),
                 'pool':pd.DataFrame({'Name':['A'], 'Projection':[12.]})}
        return SimpleNamespace(session_state=state, toast=lambda x:None,
                               warning=lambda x:None, error=lambda x:self.fail(x))

    def test_unchanged_rerun_does_not_copy_or_queue_again(self):
        app = self.app()
        with patch.object(persistence, 'advance'):
            persistence.schedule(app)
            cp = app.session_state['_slate_active']['_session_checkpoint']
            app.session_state['_slate_backup_queue'].clear()
            with patch('simmah_session_workspaces.deepcopy', side_effect=AssertionError('copied')):
                persistence.schedule(app)
            self.assertIs(app.session_state['_slate_active']['_session_checkpoint'], cp)
            self.assertFalse(app.session_state['_slate_backup_queue'])

    def test_in_place_edits_queue_isolated_latest_values(self):
        app = self.app()
        with patch.object(persistence, 'advance'):
            persistence.schedule(app)
            previous = app.session_state['_slate_active']['_session_checkpoint']
            app.session_state['outcomes'][0,0] = 900
            app.session_state['pool'].loc[0,'Projection'] = 44.
            persistence.schedule(app)
            pending, revision = app.session_state['_slate_backup_queue']['dk']
            self.assertGreater(revision, 1)
            self.assertEqual(previous['values']['outcomes'][0,0], 0)
            self.assertEqual(pending['checkpoint']['values']['pool'].Projection.iloc[0], 44.)
            app.session_state['outcomes'][0,0] = 901
            self.assertEqual(pending['checkpoint']['values']['outcomes'][0,0], 900)

    def test_restored_unchanged_backup_is_not_resaved(self):
        app = self.app()
        row = app.session_state['_slate_active']
        row['_session_checkpoint'] = checkpoint(app)
        app.session_state['_slate_backup_refs'] = {'dk':{'digest':'verified'}}
        with patch.object(persistence, 'advance'):
            persistence.schedule(app)
        self.assertFalse(app.session_state.get('_slate_backup_queue'))

    def test_fingerprint_changes_with_nested_edits_and_uploads(self):
        from simmah_slate_workspaces import StoredUpload
        values = {'frame':pd.DataFrame({'X':[{'lock':False}]}),
                  'upload':StoredUpload(b'original','entries.csv')}
        first = fingerprint(values)
        self.assertEqual(first, fingerprint(values))
        values['frame'].iloc[0,0]['lock'] = True
        self.assertNotEqual(first, fingerprint(values))
        second = fingerprint(values)
        values['upload'] = StoredUpload(b'edited','entries.csv')
        self.assertNotEqual(second, fingerprint(values))

    def test_click_returns_while_worker_is_blocked_and_preserves_click_state(self):
        app = self.app()
        context = dict(format='DraftKings Showdown', contest_id='123', kind='entries',
                       player_pool=app.session_state['pool'])
        entered, release = threading.Event(), threading.Event()
        make = exports.make_checkpoint
        def blocked(*args):
            entered.set()
            if not release.wait(10): raise TimeoutError('test worker was not released')
            return make(*args)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(exports, 'make_checkpoint', side_effect=blocked), \
                patch.object(exports, 'persist_checkpoint', return_value=Path(folder)/'audit.zip'):
            try:
                exports.queue_export(app, b'exact csv', 'entries.csv', context)
                self.assertTrue(entered.wait(5))
                jobs = app.session_state['_slate_export_jobs']
                self.assertFalse(jobs[0]['future'].done())
                self.assertNotIn(exports.HISTORY, app.session_state)
                app.session_state['salary'] = 100
                app.session_state['pool'].loc[0,'Projection'] = 99.
            finally:
                release.set()
            jobs[0]['future'].result(timeout=10)
            self.assertTrue(exports.finish_exports(app))
        record = app.session_state[exports.HISTORY][0]
        with zipfile.ZipFile(io.BytesIO(record['archive'])) as bundle:
            self.assertEqual(bundle.read('export.csv'), b'exact csv')
            state = {};restore(state, bundle.read('workspace_snapshot.txt').decode())
            self.assertEqual(state['salary'], 49000)
            self.assertEqual(state['pool'].Projection.iloc[0], 12.)
        self.assertFalse(exports.finish_exports(app))

    def test_repeated_clicks_keep_order_and_follow_original_slate_after_switch(self):
        app = self.app()
        context = dict(format='DraftKings Showdown', contest_id='123', kind='entries')
        with patch.object(exports, 'persist_checkpoint'):
            exports.queue_export(app, b'one', 'entries.csv', context)
            exports.queue_export(app, b'two', 'entries.csv', context)
            for job in app.session_state['_slate_export_jobs']:
                job['future'].result(timeout=10)
            row = app.session_state['_slate_active']
            row['_session_checkpoint'] = checkpoint(app)
            app.session_state['_slate_active'] = dict(id='fd')
            exports.finish_exports(app)
        self.assertNotIn(exports.HISTORY, app.session_state)
        history = row['_session_checkpoint']['values'][exports.HISTORY]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1]['parent_export_id'], history[0]['export_id'])
        self.assertNotIn('_slate_archive_pending', row['_session_checkpoint']['values'])

    def test_random_arrays_skip_deflate_but_compressible_arrays_stay_small(self):
        from simmah_workspace_backup import pack, unpack
        random = np.random.default_rng(5).normal(size=300000)
        payload = dict(record=dict(id='dk'), checkpoint=dict(values=dict(random=random, zeros=np.zeros(300000))))
        raw = pack(payload)
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            arrays = [info for info in bundle.infolist() if info.filename.endswith('.npy')]
            self.assertEqual({info.compress_type for info in arrays}, {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
            zeros = min(arrays, key=lambda info:info.compress_size)
            self.assertLess(zeros.compress_size, 20000)
        restored = unpack(raw)
        np.testing.assert_array_equal(restored['checkpoint']['values']['random'], random)
        np.testing.assert_array_equal(restored['checkpoint']['values']['zeros'], np.zeros(300000))
