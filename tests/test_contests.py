import unittest
import numpy as np,pandas as pd
from simmah_contests import evaluate_contest,payout_vector,lineup_indices,score_batch


class ContestAccountingTest(unittest.TestCase):
    def test_duplicate_tie_splits_every_occupied_prize(self):
        values=pd.DataFrame({'A':[5.],'B':[5.],'C':[0.]})
        users=pd.DataFrame({'S':['A']});field=pd.DataFrame({'S':['B','B','C','C']})
        result=evaluate_contest(values,users,field,['S'],5,[(1,1,100),(2,2,60),(3,3,20)],10)
        self.assertEqual(result['Expected Prize ($)'].iloc[0],60)
        self.assertAlmostEqual(result['WinRate'].iloc[0],1/3)
        self.assertEqual(result['CashRate'].iloc[0],1)
        self.assertEqual(result['FieldRank'].iloc[0],2)

    def test_joint_portfolio_competes_and_conserves_prize_pool(self):
        values=pd.DataFrame({'A':[5.],'B':[5.],'C':[0.]})
        users=pd.DataFrame({'S':['A','B','C','C','C']});field=pd.DataFrame({'S':['C']})
        result=evaluate_contest(values,users,field,['S'],5,[(1,1,100),(2,2,60),(3,3,20)],10,joint=True)
        self.assertAlmostEqual(result['Expected Prize ($)'].sum(),180)
        self.assertEqual(result['Expected Prize ($)'].iloc[0],80)
        self.assertEqual(result['Expected Prize ($)'].iloc[1],80)
        self.assertAlmostEqual(result['WinRate'].sum(),1)

    def test_representative_field_scaling_is_explicit(self):
        values=pd.DataFrame({'A':[5.],'B':[5.],'C':[0.]})
        users=pd.DataFrame({'S':['A']});field=pd.DataFrame({'S':['B','C']})
        result=evaluate_contest(values,users,field,['S'],5,[(1,1,100),(2,2,60),(3,3,20)],10)
        self.assertEqual(result['Expected Prize ($)'].iloc[0],60)
        self.assertTrue(result.attrs['field_is_estimated'])
        self.assertEqual(result.attrs['representative_opponents'],2)

    def test_all_ten_thousand_outcomes_used(self):
        values=pd.DataFrame({'A':np.r_[np.ones(9999),-1], 'B':np.zeros(10000)})
        result=evaluate_contest(values,pd.DataFrame({'S':['A']}),pd.DataFrame({'S':['B']}),['S'],2,[(1,1,2)],1)
        self.assertEqual(result.attrs['simulations'],10000)
        self.assertAlmostEqual(result['Expected Prize ($)'].iloc[0],1.9998)
        self.assertAlmostEqual(result['WinRate'].iloc[0],.9999)

    def test_multiplier_and_duplicate_slot_order(self):
        values=np.array([[10.,20.,30.]])
        frame=pd.DataFrame({'C':['A','A'],'F1':['B','C'],'F2':['C','B']})
        picks,mult=lineup_indices(frame,['C','F1','F2'],['A','B','C'],[1.5,1,1])
        np.testing.assert_array_equal(score_batch(values,picks,mult),[[65,65]])

    def test_invalid_payouts_or_player_refs_rejected(self):
        with self.assertRaises(ValueError):payout_vector(10,[(1,2,10),(2,3,5)])
        with self.assertRaises(ValueError):payout_vector(10,[(1,2,-1)])
        with self.assertRaises(ValueError):lineup_indices(pd.DataFrame({'S':['missing']}),['S'],['A'])


if __name__=='__main__':unittest.main()
