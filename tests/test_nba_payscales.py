import unittest
from simmah_nba_payscales import catalog,apply_payscale
from simmah_nba_contests import payout_vector

class PayscaleTests(unittest.TestCase):
    def test_generic_payouts_keep_current_identity(self):
        for key,total,capacity in [('piggy-bank-shot',4000,95808),('fadeaway',15000,71856),('dime-time',250,2972),('quarter-jukebox',4000,19123),('and-one',20000,23799)]:
            with self.subTest(key=key):
                profile=catalog('FanDuel')[key]
                selected={'id':'987654','name':'A future NBA contest','entry_fee':.2}
                result=apply_payscale(profile,selected,'2027-02-17','FanDuel',capacity)
                self.assertEqual(result['id'],'987654')
                self.assertEqual(result['date'],'2027-02-17')
                self.assertEqual(result['name'],selected['name'])
                self.assertEqual(result['entry_fee'],.2)
                self.assertAlmostEqual(payout_vector(result).sum(),total)
                self.assertNotIn('date',profile)
                self.assertNotIn('id',profile)

    def test_unknown_capacity_is_not_guessed(self):
        for key in ['quarter-jukebox','and-one']:
            profile=catalog('DraftKings')[key]
            self.assertIsNone(profile['capacity'])
            with self.assertRaises(ValueError):
                apply_payscale(profile,{'id':'12','name':'new','entry_fee':.25},'2027-01-01','DraftKings')

    def test_other_site_presets_not_offered(self):
        self.assertNotIn('piggy-bank-shot',catalog('DraftKings'))

    def test_too_small_capacity_rejected(self):
        with self.assertRaises(ValueError):
            apply_payscale(catalog('FanDuel')['dime-time'],{'id':'1','name':'new','entry_fee':.1},'2027-01-01','FanDuel',600)

if __name__=='__main__':unittest.main()
