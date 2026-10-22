import csv,io,unittest
from simmah_nba_swap_recovery import before_swap_csv

class SwapRecoveryTests(unittest.TestCase):
    def saved(self,size=8):return ('old-signature',{'original_entries':[['5304814248','196983215','NBA $250 Dime Time','0.10',*[str(i) for i in range(size)]]]},1.5)
    def test_original_ids_slots_and_metadata_preserved_without_signature_check(self):
        result=before_swap_csv(self.saved(),'196983215',['PG','SG','SF','PF','C','G','F','UTIL'])
        rows=list(csv.reader(io.StringIO(result.decode())))
        self.assertEqual(rows[1],self.saved()[1]['original_entries'][0])
        self.assertEqual(rows[0][-1],'UTIL')
    def test_fd_nine_slots_supported(self):
        result=before_swap_csv(self.saved(9),'196983215',list('ABCDEFGHI'))
        self.assertEqual(len(list(csv.reader(io.StringIO(result.decode())))[1]),13)
    def test_missing_corrupt_or_cross_contest_results_not_fabricated(self):
        for saved in (None,(),('x',{}),('x',{'original_entries':[]}),('x',{'original_entries':[['1','other','name','0.1']]})):
            self.assertIsNone(before_swap_csv(saved,'196983215',list('ABCDEFGH')))
        self.assertIsNone(before_swap_csv(self.saved(),'wrong',list('ABCDEFGH')))
    def test_duplicate_entry_ids_rejected(self):
        saved=self.saved();saved[1]['original_entries']*=2
        self.assertIsNone(before_swap_csv(saved,'196983215',list('ABCDEFGH')))
