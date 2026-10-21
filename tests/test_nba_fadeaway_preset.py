import unittest
from simmah_nba_contests import saved_contest,payout_vector

NAME='$18K Wed NBA Fadeaway (Only $0.25 to Enter)'
class FadeawayTests(unittest.TestCase):
    def get(self,**kw):
        args=dict(contest_id='135251-999999999',day='2026-10-21',entry_fee=.25,name=NAME,platform='FanDuel');args.update(kw)
        return saved_contest(**args)
    def test_exact_uploaded_metadata_binds_id(self):
        c=self.get();p=payout_vector(c)
        self.assertEqual(c['id'],'135251-999999999');self.assertEqual(len(p),86228)
        self.assertEqual(p.sum(),18000);self.assertEqual((p>0).sum(),25350)
        self.assertEqual(p[0],500);self.assertEqual(p[25349],.5);self.assertEqual(p[25350],0)
    def test_different_contests_do_not_match(self):
        for kw in [dict(day='2026-10-22'),dict(entry_fee=.05),dict(platform='DraftKings'),dict(name='$5K Fadeaway'),dict(name=None)]:
            self.assertIsNone(self.get(**kw))
    def test_name_whitespace_and_case_only(self):
        self.assertIsNotNone(self.get(name='  '+NAME.upper()+' '))
        self.assertIsNone(self.get(name=NAME+' (Night)'))

if __name__=='__main__':unittest.main()
