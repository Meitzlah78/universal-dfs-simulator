import io
import unittest
from simmah_build_state import uploaded_slate_signature, signature_matches_upload
class BuildStateTests(unittest.TestCase):
    def test_portfolio_rerun_keeps_same_upload_identity_and_cursor(self):
        f=io.BytesIO(b'entry,salary\n1,5000\n');f.seek(3)
        first=uploaded_slate_signature(f,'FanDuel','Single Game')
        self.assertEqual(first,uploaded_slate_signature(f,'FanDuel','Single Game'))
        self.assertEqual(f.tell(),3)
        self.assertNotEqual(first,uploaded_slate_signature(io.BytesIO(b'new slate'),'FanDuel','Single Game'))
        self.assertNotEqual(first,uploaded_slate_signature(f,'FanDuel','Full Roster'))
    def test_legacy_candidate_migration(self):
        current=('FanDuel','Single Game','filehash')
        legacy=('FanDuel','Single Game',(('A','QB','SF','10000','20'),('B','WR','WAS','8000','12')))
        self.assertTrue(signature_matches_upload(legacy,current,[('B','WR','WAS','8000'),('A','QB','SF','10000')]))
        self.assertFalse(signature_matches_upload(legacy,current,[('A','QB','SF','9999'),('B','WR','WAS','8000')]))
        self.assertFalse(signature_matches_upload(('FanDuel','Single Game','otherfile'),current,[('A','QB','SF','10000'),('B','WR','WAS','8000')]))
