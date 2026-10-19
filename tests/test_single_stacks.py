import unittest
from simmah_single_stacks import matches
class SingleStackTests(unittest.TestCase):
    def setUp(self):
        self.lookup={str(i):{'Team':'A' if i<5 else 'B','Position':'WR'} for i in range(10)}
    def chosen(self,ids):return dict(zip(['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5'],map(str,ids)))
    def test_splits_and_any(self):
        for ids,split in [([0,1,2,5,6,7],'3–3'),([0,1,2,3,5,6],'4–2'),([0,1,2,3,4,5],'5–1')]:
            c=self.chosen(ids)
            self.assertTrue(matches(c,self.lookup,['Any / All']))
            self.assertTrue(matches(c,self.lookup,[split]))
            self.assertFalse(matches(c,self.lookup,[s for s in ['3–3','4–2','5–1'] if s!=split]))
        self.assertTrue(matches(self.chosen([0,1,2,3,5,6]),self.lookup,['3–3','4–2']))
    def test_each_qb_needs_own_receiver(self):
        self.lookup['0']['Position']='QB';self.lookup['5']['Position']='QB'
        c=self.chosen([0,1,2,3,4,5])
        self.assertFalse(matches(c,self.lookup,['Any / All'],True))
        self.assertTrue(matches(self.chosen([0,1,2,3,5,6]),self.lookup,['4–2'],True))
