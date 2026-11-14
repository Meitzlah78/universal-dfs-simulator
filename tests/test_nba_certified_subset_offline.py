import unittest
import pandas as pd
from scripts.certified_nba_subset_offline import select_team_snapshots

class SubsetTests(unittest.TestCase):
    def data(self):
        rows=[dict(package='p',game_id='g',team='MIL',name=str(i),eligibility_certified=True,full_membership_verified=True) for i in range(8)]
        priors=[dict(package='p',game_id='g',team='MIL',name=str(i),supported=True) for i in range(8)]
        return pd.DataFrame(rows),pd.DataFrame(priors)
    def test_whole_team_can_qualify_only_with_all_evidence(self):
        a,p=self.data();self.assertTrue(select_team_snapshots(a,p).certified.iloc[0])
    def test_one_unknown_status_blocks_entire_snapshot(self):
        a,p=self.data();a.loc[7,'eligibility_certified']=False
        self.assertFalse(select_team_snapshots(a,p).certified.iloc[0])
    def test_missing_prior_cannot_drop_player_from_denominator(self):
        a,p=self.data();p=p.iloc[:-1]
        r=select_team_snapshots(a,p).iloc[0]
        self.assertEqual(r.pool_n,8);self.assertFalse(r.certified)
    def test_row_statuses_do_not_prove_roster_completeness(self):
        a,p=self.data();a=a.drop(columns=['full_membership_verified'])
        self.assertFalse(select_team_snapshots(a,p).certified.iloc[0])

if __name__=='__main__':unittest.main()
