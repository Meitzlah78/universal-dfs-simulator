import csv,io,unittest
import numpy as np
import test_nba_candidates
from simmah_nba_pipeline import run_pipeline,export_portfolio
from simmah_nba_import import SLOTS

class NBAPipelineTests(unittest.TestCase):
    def test_components_export_and_independent_scenario_sets(self):
        pool,_=test_nba_candidates.CandidateTests().fixture()
        pool['Player ID']=['42-'+str(i) for i in range(len(pool))]
        pool['Name']=pool['Player ID'];pool['Opponent']='E';pool['Game']='A@E'
        called=[]
        def factory(n,seed):
            called.append(seed);return np.random.default_rng(seed).gamma(4,8,(n,len(pool)))
        result=run_pipeline(pool,factory,np.full(len(pool),22.5),'synthetic balanced ownership',
            [1]*10+[0]*91,.05,5,simulations=20,candidate_target=100,field_support_target=500,diversity=0)
        self.assertEqual(len(set(called)),3)
        self.assertEqual(result['field']['copies'].sum(),100)
        self.assertEqual(len(result['portfolio']),5)
        rows=[['entry_id','contest_id','contest_name','entry_fee',*SLOTS]]
        rows += [[str(900+i),'42-99','Test','.05',*(['']*9)] for i in range(5)]
        header=['Id','Nickname','Salary','Position','Team','Opponent','Game','Injury Indicator','Injury Details','FPPG']
        rows.append(header)
        for _,p in pool.iterrows():rows.append([p['Player ID'],p['Name'],str(p['Salary']),p['Position'],p['Team'],'E','A@E','','','0'])
        f=io.StringIO();csv.writer(f).writerows(rows)
        exported=list(csv.reader(io.StringIO(export_portfolio(f.getvalue().encode(),'42-99',pool,result).decode())))
        self.assertEqual([r[0] for r in exported[1:6]],[str(900+i) for i in range(5)])
        self.assertTrue(all(len(set(r[4:13]))==9 for r in exported[1:6]))
    def test_reused_scenarios_rejected(self):
        pool,_=test_nba_candidates.CandidateTests().fixture()
        def factory(n,seed):return np.ones((n,len(pool)))
        with self.assertRaisesRegex(ValueError,'repeat construction'):
            run_pipeline(pool,factory,np.full(40,22.5),'synthetic',[1,0],.05,1,
                         simulations=5,candidate_target=10,field_support_target=10)
