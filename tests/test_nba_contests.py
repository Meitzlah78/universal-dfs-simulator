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


class SuppliedQuarterJukeboxTests(unittest.TestCase):
    def test_exact_name_site_day_and_fee_bind_to_uploaded_id(self):
        name='NBA $3K Quarter Jukebox [Just $0.25!]'
        c=saved_contest('987654321','2026-10-27',.25,name=name,platform='DraftKings')
        self.assertIsNotNone(c)
        self.assertEqual(c['id'],'987654321')
        self.assertEqual(c['capacity'],14268)
        self.assertEqual(payout_vector(c).sum(),3000)
        for day,fee,site,label in [('2026-10-28',.25,'DraftKings',name),
                ('2026-10-27',.1,'DraftKings',name),('2026-10-27',.25,'FanDuel',name),
                ('2026-10-27',.25,'DraftKings','Another contest')]:
            self.assertIsNone(saved_contest('987654321',day,fee,name=label,platform=site))
