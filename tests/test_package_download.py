import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from simmah_package_download import package_download_data,supports_deferred_download
from simmah_input_archive import Archive


class PackageDownloadTests(unittest.TestCase):
    def test_does_not_load_archive_until_click_and_freezes_original_identity(self):
        calls=[]
        archive=SimpleNamespace(get=lambda digest:calls.append(digest) or b'original package')
        st=SimpleNamespace(session_state={});reference={'digest':'a'*64}
        with patch('simmah_package_download.supports_deferred_download',return_value=True),patch('simmah_archive_ui.archive_for',return_value=archive):
            data=package_download_data(st,reference)
        self.assertEqual(calls,[])
        reference['digest']='b'*64;st.session_state['_slate_active']={'id':'other sport/site'}
        self.assertEqual(data(),b'original package');self.assertEqual(calls,['a'*64])

    def test_pending_bytes_and_older_streamlit_fallback(self):
        st=SimpleNamespace(session_state={'_slate_archive_pending':{'a'*64:{'raw':b'pending'}}});reference={'digest':'a'*64}
        with patch('simmah_package_download.supports_deferred_download',return_value=True):
            self.assertEqual(package_download_data(st,reference),b'pending')
        with patch('simmah_package_download.supports_deferred_download',return_value=False),patch('simmah_nba_diagnostics.package_bytes',return_value=b'legacy') as old:
            self.assertEqual(package_download_data(st,reference),b'legacy');old.assert_called_once()

    def test_deferred_real_archive_keeps_hash_verification(self):
        raw=b'complete calibration zip';digest=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            archive=Archive(root,'a'*32)
            path=archive.root/'objects'/digest;path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
            with patch('simmah_package_download.supports_deferred_download',return_value=True),patch('simmah_archive_ui.archive_for',return_value=archive):
                data=package_download_data(SimpleNamespace(session_state={}),{'digest':digest})
            self.assertEqual(data(),raw)
            path.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):data()

    def test_installed_streamlit_capability_detection(self):
        self.assertIsInstance(supports_deferred_download(),bool)


class DeferredDownloadUITests(unittest.TestCase):
    def test_streamlit_renders_download_without_loading_archive(self):
        from streamlit.testing.v1 import AppTest
        calls=[]
        archive=SimpleNamespace(get=lambda digest:calls.append(digest) or b'package')
        app_source='''
import streamlit as st
from simmah_package_download import package_download_data
value=package_download_data(st,{'digest':'a'*64})
st.download_button('Download calibration package',value,file_name='package.zip',on_click='ignore')
'''
        with patch('simmah_package_download.supports_deferred_download',return_value=True),patch('simmah_archive_ui.archive_for',return_value=archive):
            app=AppTest.from_string(app_source).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('download_button')),1)
        self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
