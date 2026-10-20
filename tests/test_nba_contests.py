import unittest
from simmah_nba_contests import saved_contest,payout_vector

class NBAContestPresetTests(unittest.TestCase):
    def test_uploaded_contest_payouts_and_identity(self):
        c=saved_contest('135251-281018991','2026-10-20',.05)
        p=payout_vector(c)
        self.assertEqual(len(p),259740);self.assertAlmostEqual(p.sum(),15000)
        self.assertEqual(p[0],500);self.assertEqual(p[109999],.1);self.assertEqual(p[110000],0)
        with self.assertRaises(ValueError):saved_contest(c['id'],'2026-10-21',.05)
        self.assertIsNone(saved_contest('../other','2026-10-20',.05))
    def test_missing_or_overlapping_prizes_rejected(self):
        c=saved_contest('135251-281018991','2026-10-20',.05)
        c['payout_tiers'][1]['first']=1
        with self.assertRaises(ValueError):payout_vector(c)

class DraftKingsContestTests(unittest.TestCase):
    def test_numeric_dk_id_loads_verified_payouts(self):
        contest=saved_contest('196711762','2026-10-20',.25)
        self.assertIsNotNone(contest)
        self.assertEqual(contest['capacity'],7134)
        self.assertAlmostEqual(payout_vector(contest).sum(),1500)
        with self.assertRaises(ValueError):saved_contest('196711762','2026-10-20',.10)
