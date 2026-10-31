import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from simmah_leverage import candidate_opportunities,attach_leverage

class LeverageTest(unittest.TestCase):
    def fixture(self,role='Captain'):
        candidates=pd.DataFrame({role:['A','B'],'Flex1':['C']*2,'Flex2':['D']*2,'Flex3':['E']*2,'Flex4':['F']*2,'Flex5':['G']*2})
        outcomes=pd.DataFrame({'A':[10.,0.],'B':[0.,20.],**{n:[1.,1.] for n in 'CDEFG'}})
        return outcomes,candidates
    def test_all_formats_and_multiplier(self):
        for role in ['Captain','MVP']:
            o,c=self.fixture(role);r=candidate_opportunities(o,c).set_index('Name');prefix='CPT' if role=='Captain' else 'MVP'
            self.assertEqual(r.loc['A','Candidate Best %'],50)
            self.assertEqual(r.loc['A',prefix+' Candidate Best %'],50)
            self.assertEqual(r.loc['C','FLEX Candidate Best %'],100)
            self.assertAlmostEqual(r['Candidate Best %'].sum(),600)
        for defense in ['D','DST']:
            slots=['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX',defense]
            c=pd.DataFrame([list('ABCDEFGHI'),list('ABCDEFGHJ')],columns=slots)
            o=pd.DataFrame({n:[1.,1.] for n in 'ABCDEFGHIJ'});o['I']=[10.,0.];o['J']=[0.,20.]
            r=candidate_opportunities(o,c).set_index('Name')
            self.assertEqual(r.loc['I','Candidate Best %'],50);self.assertAlmostEqual(r['Candidate Best %'].sum(),900)
    def test_ties_and_duplicate_rosters_do_not_bias_share(self):
        o,c=self.fixture();o['A']=5.;o['B']=5.
        c=pd.concat([c,c.iloc[[0]]],ignore_index=True)
        r=candidate_opportunities(o,c)
        self.assertEqual(r.attrs['candidates'],2)
        self.assertEqual(r.set_index('Name').loc['A','CPT Candidate Best %'],50)
    def test_captain_bonus_changes_best_roster(self):
        o=pd.DataFrame({'A':[10.],'B':[8.],'C':[1.],'D':[1.],'E':[1.],'F':[1.]})
        c=pd.DataFrame([['A','B','C','D','E','F'],['B','A','C','D','E','F']],columns=['MVP','Flex1','Flex2','Flex3','Flex4','Flex5'])
        r=candidate_opportunities(o,c).set_index('Name');self.assertEqual(r.loc['A','MVP Candidate Best %'],100)
    def test_ownership_priority_zero_and_role_baselines(self):
        o,c=self.fixture();op=candidate_opportunities(o,c)
        p=pd.DataFrame({'Name':['A','B','C'],'Projected Own %':[0,np.nan,80], 'Field Own %':[20,70,90], 'Field CPT Own %':[10,30,0],'Field FLEX Own %':[10,40,90]})
        r=attach_leverage(p,op)
        self.assertEqual(r['Leverage (pp)'].tolist(),[50,-20,20])
        self.assertEqual(r['Leverage Ownership Source'].tolist(),['Projected ownership','Simulated field estimate','Projected ownership'])
        self.assertEqual(r['CPT Leverage (pp)'].tolist(),[40,20,0])
    def test_missing_inputs_are_pending_not_zero(self):
        o,c=self.fixture();p=pd.DataFrame({'Name':['A']})
        r=attach_leverage(p,candidate_opportunities(o,c));self.assertTrue(r['Leverage (pp)'].isna().all())
        for outcomes,candidates in [(None,c),(o,None),(o.drop(columns='A'),c),(o*float('nan'),c)]:
            r=attach_leverage(p,candidate_opportunities(outcomes,candidates));self.assertTrue(r['Candidate Best %'].isna().all())
    def test_app_shares_cached_metric_in_both_platform_paths(self):
        s=Path('dfs_app.py').read_text()
        self.assertIn('fd_player_display = attach_leverage',s);self.assertIn('player_display = attach_leverage',s)
        self.assertIn('def leverage_opportunities_cached(outcomes, candidates):',s)
