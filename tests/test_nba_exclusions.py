import unittest
import numpy as np
import pandas as pd
from simmah_nba_exclusions import excluded_player_indices,game_options
from simmah_nba_pipeline import run_pipeline
import test_nba_candidates


class ExclusionTests(unittest.TestCase):
    def test_games_include_both_sides_and_team_excludes_only_one(self):
        p=pd.DataFrame({'Team':['NYK','PHI','GSW','LAL'],'Opponent':['PHI','NY','LAL','GS']})
        self.assertEqual(set(game_options(p)),{'NY vs PHI','GS vs LAL'})
        np.testing.assert_array_equal(excluded_player_indices(p,games=['NY vs PHI']),[0,1])
        np.testing.assert_array_equal(excluded_player_indices(p,teams=['NY']),[0])
        np.testing.assert_array_equal(excluded_player_indices(p,games=['NY vs PHI'],teams=['GSW']),[0,1,2])
        self.assertEqual(len(excluded_player_indices(p)),0)

    def test_unloaded_selection_fails(self):
        p=pd.DataFrame({'Team':['NY'],'Opponent':['PHI']})
        with self.assertRaises(ValueError):excluded_player_indices(p,teams=['LAL'])

    def test_both_platforms_exclude_user_candidates_but_keep_opponents(self):
        for platform in ['DraftKings','FanDuel']:
            with self.subTest(platform=platform):
                pool,_=test_nba_candidates.CandidateTests().fixture();pool.attrs['platform']=platform
                pool['Opponent']='E';pool['Name']=pool['Player ID']
                before=pool.copy(deep=True)
                excluded=excluded_player_indices(pool,teams=['A'])
                def factory(n,seed):return np.random.default_rng(seed).gamma(4,8,(n,len(pool)))
                r=run_pipeline(pool,factory,np.ones(len(pool)),'synthetic relative popularity',
                    [1]*10+[0]*91,.05,3,simulations=128,candidate_target=500,
                    field_support_target=100,diversity=0,ownership_mode='relative popularity',excluded_indices=excluded)
                self.assertFalse(np.isin(r['candidates']['indices'],excluded).any())
                self.assertTrue(np.isin(r['field']['indices'],excluded).any())
                self.assertEqual(set(r['excluded_player_ids']),set(pool.iloc[excluded]['Player ID']))
                pd.testing.assert_frame_equal(pool,before)

    def test_invalid_index_never_wraps_to_last_player(self):
        pool,_=test_nba_candidates.CandidateTests().fixture()
        with self.assertRaisesRegex(ValueError,'indices'):
            run_pipeline(pool,None,np.ones(len(pool)),'test',[1,0],.05,1,excluded_indices=[-1])


if __name__=='__main__':unittest.main()
