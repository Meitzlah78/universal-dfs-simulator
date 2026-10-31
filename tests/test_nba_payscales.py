import unittest
from simmah_nba_payscales import catalog,apply_payscale
from simmah_nba_contests import payout_vector

class PayscaleTests(unittest.TestCase):
    def test_generic_payouts_keep_current_identity(self):
        for key,total,capacity in [('piggy-bank-shot',4000,95808),('fadeaway',15000,71856),('dime-time',250,2972),('quarter-jukebox',4000,19024),('and-one',20000,23781)]:
            with self.subTest(key=key):
                site='FanDuel' if key in ('piggy-bank-shot','fadeaway') else 'DraftKings'
                profile=catalog(site)[key]
                selected={'id':'987654','name':'A future NBA contest','entry_fee':.2}
                result=apply_payscale(profile,selected,'2027-02-17',site,capacity)
                self.assertEqual(result['id'],'987654')
                self.assertEqual(result['date'],'2027-02-17')
                self.assertEqual(result['name'],selected['name'])
                self.assertEqual(result['entry_fee'],.2)
                self.assertAlmostEqual(payout_vector(result).sum(),total)
                self.assertNotIn('date',profile)
                self.assertNotIn('id',profile)

    def test_confirmed_capacities(self):
        for key,capacity in [('quarter-jukebox',19024),('and-one',23781)]:
            profile=catalog('DraftKings')[key]
            result=apply_payscale(profile,{'id':'12','name':'new','entry_fee':.25},'2027-01-01','DraftKings')
            self.assertEqual(result['capacity'],capacity)

    def test_other_site_presets_not_offered(self):
        self.assertNotIn('piggy-bank-shot',catalog('DraftKings'))
        self.assertNotIn('fadeaway',catalog('DraftKings'))
        for key in ['dime-time','quarter-jukebox','and-one']:
            self.assertNotIn(key,catalog('FanDuel'))

    def test_supplied_14268_schedule_keeps_uploaded_identity_and_exact_payouts(self):
        for site in ['DraftKings']:
            profile=catalog(site)['nba-3000-14268']
            selected={'id':'987654','name':'Uploaded NBA contest','entry_fee':.25}
            result=apply_payscale(profile,selected,'2026-10-27',site)
            payouts=payout_vector(result)
            self.assertEqual(len(payouts),14268)
            self.assertEqual(payouts.sum(),3000)
            self.assertEqual((payouts>0).sum(),3419)
            self.assertEqual(list(payouts[:6]),[150,100,60,45,35,25])
            self.assertEqual(payouts[120],1.5)
            self.assertEqual(payouts[255],1)
            self.assertEqual(payouts[610],.75)
            self.assertEqual(payouts[1490],.5)
            self.assertEqual(payouts[3418],.5)
            self.assertEqual(payouts[3419],0)
            self.assertEqual(result['id'],selected['id'])
            self.assertEqual(result['entry_fee'],selected['entry_fee'])
            self.assertNotIn('max_entries',profile)
            self.assertEqual(profile['platform'],'DraftKings')
        self.assertNotIn('nba-3000-14268',catalog('FanDuel'))

    def test_new_payscale_renders_without_guessing_an_entry_limit(self):
        from types import SimpleNamespace
        from simmah_nba_payscales import render_panel
        captions=[]
        st=SimpleNamespace(write=lambda *a:None,selectbox=lambda *a,**kw:'nba-3000-14268',
            number_input=lambda *a,**kw:kw['value'],caption=captions.append)
        selected={'id':'987654','name':'Uploaded contest','entry_fee':.25}
        result=render_panel(st,None,selected,'2026-10-27','DraftKings')
        self.assertEqual(result['capacity'],14268)
        self.assertEqual(result['id'],'987654')
        self.assertNotIn('entries max',' '.join(captions))

    def test_too_small_capacity_rejected(self):
        with self.assertRaises(ValueError):
            apply_payscale(catalog('DraftKings')['dime-time'],{'id':'1','name':'new','entry_fee':.1},'2027-01-01','DraftKings',600)

if __name__=='__main__':unittest.main()
