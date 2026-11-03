import importlib.util
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

spec=importlib.util.spec_from_file_location('ranking_challengers',Path(__file__).resolve().parents[1]/'scripts'/'compare_portfolio_rankings.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class RankingChallengerTests(unittest.TestCase):
    def test_joint_ties_include_all_own_entries(self):
        ranks,prizes=m.joint_prizes([100,100],[100],[[1,1,9],[2,2,6],[3,3,3]])
        np.testing.assert_array_equal(ranks,[1,1]);np.testing.assert_allclose(prizes,[6,6])
        self.assertEqual(prizes.sum(),12)

    def test_joint_non_ties_keep_own_ranks(self):
        ranks,prizes=m.joint_prizes([110,80],[100,90],[[1,1,10],[2,2,5]])
        np.testing.assert_array_equal(ranks,[1,4]);np.testing.assert_allclose(prizes,[10,0])

    def test_outcome_columns_cannot_change_selection_or_relax_caps(self):
        rows=[{'A':a,'B':b,'_top1':(i+1)/30,'_win':(30-i)/30,'_prize':i+2,'_mean':30-i,'actual_points':i}
              for i,(a,b) in enumerate(( (a,b) for a in 'ABCDEF' for b in 'ABCDEF' if a!=b))]
        frame=pd.DataFrame(rows);controls={'F':{'Max Exposure %':25}}
        first=m.select_challengers(frame,['A','B'],4,controls,0)
        frame['actual_points']=frame.actual_points.iloc[::-1].to_numpy()*1000
        second=m.select_challengers(frame,['A','B'],4,controls,0)
        for method in m.METHODS:
            self.assertNotIn('error',first[method]);self.assertNotIn('error',second[method])
            one=first[method]['portfolio'][['A','B']];two=second[method]['portfolio'][['A','B']]
            pd.testing.assert_frame_equal(one,two)
            self.assertLessEqual(one.eq('F').to_numpy().sum(),1)

if __name__=='__main__':unittest.main()
