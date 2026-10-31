from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from simmah_input_archive import Archive
from simmah_saved_cleanup import matches, clear_archive, reset_state

DAY = '2026-10-25'


def stamp(day):
    return datetime.fromisoformat(day + 'T12:00:00').replace(tzinfo=ZoneInfo('America/New_York')).timestamp()


class CleanupTest(unittest.TestCase):
    def test_date_and_platform_scope(self):
        self.assertTrue(matches(dict(filename='DKEntries.csv', saved_at=stamp(DAY)), DAY))
        self.assertTrue(matches(dict(name='FanDuel-2026-10-25-entries.csv'), DAY))
        self.assertFalse(matches(dict(name='FanDuel-2026-10-24-entries.csv', updated=stamp(DAY)*1000), DAY))
        self.assertFalse(matches(dict(filename='other.csv', saved_at=stamp(DAY)), DAY))
        self.assertTrue(matches(dict(filename='original.csv', saved_at=stamp(DAY), metadata={'platform':'DraftKings'}), DAY))
        self.assertFalse(matches(dict(filename='DKEntries.csv', saved_at=stamp('2026-10-24')), DAY))

    def test_delete_owner_and_date_only_with_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Archive(directory, 'a'*32)
            other = Archive(directory, 'b'*32)
            old = archive.put(b'old', 'FanDuel-2026-10-24.csv')
            new = archive.put(b'new', 'DKEntries-2026-10-25.csv')
            protected = other.put(b'new', 'DKEntries-2026-10-25.csv')
            with archive.connect() as db:
                db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)', ('job', new['digest'], new['digest'], 'completed', '', 0))
            path=archive.root/'jobs'/'job';path.mkdir(parents=True);(path/'result.zip').write_bytes(b'report')
            deleted=clear_archive(archive, DAY)
            self.assertEqual(deleted, {new['digest']})
            self.assertEqual([r['digest'] for r in archive.files()], [old['digest']])
            self.assertEqual(archive.get(old['digest']), b'old')
            self.assertEqual(other.get(protected['digest']), b'new')
            self.assertFalse(path.exists())
            self.assertEqual(archive.jobs(), [])

    def test_reset_drops_stale_transfers_and_preserves_older_slates(self):
        state={'_slate_records': {'old':dict(name='DKEntries-2026-10-24.csv'), 'new':dict(name='FanDuel-2026-10-25.csv')},
               '_slate_pending': {'id':'new'}, '_slate_download_transfer': {'raw':'stale'},
               '_slate_archive_pending': {'data':b'stale'}, '_slate_cleanup_browser': {'event':'one'},
               'fd_saved_builds': {'stale':1}, 'loaded_slates_browser': {'selected':{'id':'new'}}}
        reset_state(state, DAY)
        self.assertEqual(set(state['_slate_records']), {'old'})
        self.assertTrue(state['_slate_fresh_mode'])
        self.assertNotIn('fd_saved_builds', state)
        self.assertNotIn('_slate_pending', state)
        self.assertNotIn('_slate_download_transfer', state)
        self.assertNotIn('_slate_archive_pending', state)

    def test_active_calibration_does_not_delete_original(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Archive(directory, 'a'*32)
            new = archive.put(b'new', 'DKEntries-2026-10-25.csv')
            with archive.connect() as db:
                db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)', ('job',new['digest'],new['digest'],'running','',0))
            with self.assertRaisesRegex(ValueError, 'still running'):
                clear_archive(archive, DAY)
            self.assertEqual(archive.get(new['digest']), b'new')


if __name__ == '__main__': unittest.main()

class FreshWorkspaceTest(unittest.TestCase):
    def test_fresh_mode_keeps_new_build_through_reruns(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('''
import streamlit as st
from unittest.mock import patch
from simmah_slate_workspaces import begin_workspaces, finish_workspaces
st.session_state['_slate_fresh_mode'] = True
with patch('simmah_saved_cleanup.render_cleanup'), patch('simmah_slate_transport.handle_browser_transfer') as restore, patch('simmah_archive_ui.handle_archive_transfer') as archive:
    host=begin_workspaces(st)
    assert not restore.called and not archive.called
    if st.button('Build'):
        st.session_state['new_build'] = [1, 2, 3]
    st.write(str(st.session_state.get('new_build', [])))
    finish_workspaces(st, host)
''').run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['new_build'], [1,2,3])
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['new_build'], [1,2,3])
