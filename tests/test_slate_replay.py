import unittest
import numpy as np
import pandas as pd

from simmah_slate_replay import (canonical, payout_schedule, replacement_prizes,
    exposure_matrix, exposure_limits, random_portfolios, official_scores, published_player_scores)


class ReplayTest(unittest.TestCase):
    def test_dk_captain_score_is_normalized_once(self):
        frame=pd.DataFrame({'Player':['A','A'],'FPTS':[10.,15.],'Roster Position':['FLEX','CPT']})
        self.assertEqual(published_player_scores(frame,True),{'a':10.})
        with self.assertRaises(ValueError):
            published_player_scores(frame,False)

    def test_empty_fd_entries_keep_last_place_without_becoming_zero_point_entries(self):
        frame=pd.DataFrame({'Points':[10.,-4.,None],'Rank':[1,2,3],'Lineup':['roster','roster',None]})
        scores=official_scores(frame)
        self.assertLess(scores[2],scores[1])
        np.testing.assert_array_equal(replacement_prizes([[0]],scores,[10.,4.,2.,0.]),[[4.]])
        frame.loc[2,'Rank']=1
        with self.assertRaises(ValueError):
            official_scores(frame)

    def test_entire_tie_spanning_paid_and_unpaid_places_splits_prize_mass(self):
        result = replacement_prizes([[100, 100]], [100, 90], [10., 4., 0., 0.])
        np.testing.assert_allclose(result, [[14/3, 14/3]])

    def test_portfolio_entries_change_each_others_ranks(self):
        result = replacement_prizes([[110, 100]], [105, 95], [10., 4., 2., 0.])
        np.testing.assert_array_equal(result, [[10., 2.]])

    def test_all_entries_share_all_prizes_when_everyone_ties(self):
        result = replacement_prizes([[100]*4], [], [10., 4., 2., 0.])
        self.assertEqual(result.sum(), 16.)

    def test_batch_matches_individual_replacements_and_rejects_ghost_count(self):
        portfolios = [[120, 100], [110, 110], [95, 85]]
        batched = replacement_prizes(portfolios, [110, 100], [10., 4., 2., 0.])
        for i, portfolio in enumerate(portfolios):
            np.testing.assert_array_equal(batched[i], replacement_prizes(portfolio, [110, 100], [10., 4., 2., 0.])[0])
        with self.assertRaises(ValueError):
            replacement_prizes([[1]], [1], [10.])

    def test_payout_schedule_rejects_overlap_or_wrong_prize_mass(self):
        np.testing.assert_array_equal(payout_schedule([[1,1,10],[2,3,2]], 4, 14), [10,2,2,0])
        for tiers, total in [([[1,2,10],[2,3,2]],24), ([[1,1,10]],9), ([[0,1,10]],10)]:
            with self.assertRaises(ValueError):
                payout_schedule(tiers,4,total)

    def test_special_role_is_part_of_identity_but_flex_order_is_not(self):
        self.assertEqual(canonical(['a','b','c','d','e','f']), canonical(['a','f','e','d','c','b']))
        self.assertNotEqual(canonical(['a','b','c','d','e','f']),canonical(['b','a','c','d','e','f']))
        with self.assertRaises(ValueError):
            canonical(['a']*6)

    def test_random_portfolios_enforce_all_bounds_without_duplicate_picks(self):
        incidence = np.array([[1,0],[0,1],[1,0],[0,1]])
        picks, attempted = random_portfolios(4,2,incidence,np.array([1,1]),np.array([1,1]),draws=100,seed=83)
        np.testing.assert_array_equal(incidence[picks].sum(axis=1), np.ones((100,2)))
        self.assertTrue(all(len(set(p))==2 for p in picks))
        np.testing.assert_array_equal(picks, random_portfolios(4,2,incidence,np.array([1,1]),np.array([1,1]),draws=100,seed=83)[0])
        self.assertGreater(attempted,100)
        with self.assertRaises(ValueError):
            random_portfolios(4,2,incidence,np.array([3,3]),np.array([3,3]),draws=1)

    def test_manual_lock_fade_and_special_role_constraints(self):
        controls = {'a': {'Lock':True}, 'b': {'Fade':True},
                    'c': {'Min Exposure %':90, 'Max Exposure %':95, 'Captain Max %':20}}
        lower, upper = exposure_limits(['a','b','c'],controls,20,80,'Captain')
        np.testing.assert_array_equal(lower,[20,0,18,0,0,0])
        np.testing.assert_array_equal(upper,[20,0,19,20,20,4])
        m=exposure_matrix([('a',('b','c','d','e','f'))],list('abcdef'))
        self.assertEqual(m.sum(),7)
        self.assertEqual(m[0,6],1)
