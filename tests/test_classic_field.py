import unittest
import numpy as np
from simmah_classic_field import classic_tournament_mask


class ClassicFieldTest(unittest.TestCase):
    def test_running_back_does_not_satisfy_qb_pass_catcher_stack(self):
        positions=np.array(['QB','RB','RB','WR','WR','WR','TE','TE','DST'])
        teams=np.array(['A','A','B','C','D','E','F','G','H'])
        picks=np.arange(9)[None,:]
        self.assertFalse(classic_tournament_mask(picks,teams,positions)[0])
        for slot in [3,6,7]:
            changed=teams.copy();changed[slot]='A'
            self.assertTrue(classic_tournament_mask(picks,changed,positions)[0])

    def test_duplicate_players_and_nine_same_team_are_rejected(self):
        positions=['QB','RB','RB','WR','WR','WR','TE','TE','DST']
        picks=np.arange(9)[None,:]
        self.assertFalse(classic_tournament_mask(picks,['A']*9,positions)[0])
        duplicate=picks.copy();duplicate[0,2]=duplicate[0,1]
        self.assertFalse(classic_tournament_mask(duplicate,['A']*8+['B'],positions)[0])
        self.assertTrue(classic_tournament_mask(picks,['A']*8+['B'],positions)[0])

    def test_fanduel_four_player_team_limit(self):
        positions=['QB','RB','RB','WR','WR','WR','TE','TE','D']
        picks=np.arange(9)[None,:]
        teams=['A','A','B','A','A','C','A','D','E']
        self.assertFalse(classic_tournament_mask(picks,teams,positions,max_from_team=4)[0])
        teams[6]='B'
        self.assertTrue(classic_tournament_mask(picks,teams,positions,max_from_team=4)[0])

    def test_empty_batches_are_supported(self):
        self.assertEqual(len(classic_tournament_mask(np.empty((0,9),int),[],[])),0)

if __name__=='__main__':unittest.main()
