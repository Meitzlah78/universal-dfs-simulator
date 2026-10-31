import tempfile,unittest
from pathlib import Path
from simmah_saved_contests import record,merge,save,load,restore

class SavedContestsTests(unittest.TestCase):
    def contest(self):return {'id':'123','name':'Contest','entry_fee':.25,'field_size':100,'payouts':[[1,1,10],[2,5,1]],'your_entries':20,'entry_ids':['private']}
    def test_metadata_only_and_deduplicated(self):
        r=record(self.contest(),'FanDuel Single Game');self.assertNotIn('entry_ids',r);self.assertNotIn('your_entries',r)
        self.assertEqual(len(merge({'contests':[r,r]})['contests']),1)
    def test_restore_keeps_current_entry_count_and_identity(self):
        r=record(self.contest(),'FanDuel Single Game');a={'id':'123','your_entries':7}
        result=restore(a,r,'FanDuel Single Game');self.assertEqual(result['your_entries'],7);self.assertEqual(result['field_size'],100)
        for active,fmt in [({'id':'other'},'FanDuel Single Game'),(a,'DraftKings Showdown')]:
            with self.assertRaises(ValueError):restore(active,r,fmt)
    def test_backup_round_trip(self):
        r=record(self.contest(),'FanDuel Single Game')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'contests.json';save(path,{'contests':[r]});self.assertEqual(load(path),{'schema':1,'contests':[r]})
    def test_invalid_payout_or_capacity_rejected(self):
        for changes in [{'payouts':[[1,2,10],[2,3,5]]},{'field_size':2},{'entry_fee':float('nan')}]:
            with self.assertRaises(ValueError):record({**self.contest(),**changes},'FanDuel Single Game')

if __name__=='__main__':unittest.main()
