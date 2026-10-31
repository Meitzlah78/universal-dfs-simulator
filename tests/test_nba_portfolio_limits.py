import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_nba_portfolio_limits import portfolio_limits,validate_portfolio_limits
from simmah_nba_contest import select_entries
from simmah_nba_pipeline import export_portfolio
from simmah_nba_rules import rules_for

class LimitsTests(unittest.TestCase):
    def pool(self,site):
        n=30
        p=pd.DataFrame({'Player ID':[str(i) for i in range(n)],'Name':['Player '+str(i) for i in range(n)],
            'Projection':[25.]*n,'Projected Minutes':[30.]*n,'Injury Status':['Active']*n,'Eligible':[True]*n})
        p.attrs['platform']=site
        return p
    def test_trusted_ownership_and_role_caps(self):
        p=self.pool('DraftKings');p.loc[0,'Projected Minutes']=10
        p['RotoWire Projected Own %']=800/len(p)
        lim=portfolio_limits(p)
        self.assertEqual(lim['0']['Max Exposure %'],15)
        self.assertAlmostEqual(lim['1']['Max Exposure %'],800/30+5)
        p['RotoWire Projected Own %']=70
        lim=portfolio_limits(p)
        self.assertEqual(lim['1']['Max Exposure %'],60)
        with self.assertRaises(ValueError):portfolio_limits(p,{'0':{'Lock':True}})
    def test_both_sites_selection_and_tampered_export(self):
        for site in ['DraftKings','FanDuel']:
            p=self.pool(site);slots=rules_for(p)['slots'];rng=np.random.default_rng(7)
            ids=np.array([rng.choice(30,len(slots),replace=False) for _ in range(500)])
            report=pd.DataFrame({'Top 1%':rng.random(len(ids))})
            chosen=select_entries(p,ids,report,20)
            counts=chosen[list(slots)].stack().value_counts()
            self.assertLessEqual(counts.max(),12)
            chosen.loc[:,slots[0]]='0'
            with patch('simmah_nba_pipeline.export_entries') as write:
                with self.assertRaisesRegex(ValueError,'exposure cap exceeded'):
                    export_portfolio(b'',1,p,{'portfolio':chosen})
                write.assert_not_called()
    def test_infeasible_stops_instead_of_relaxing(self):
        p=self.pool('DraftKings');slots=rules_for(p)['slots']
        ids=np.array([[0,*range(1+i,8+i)] for i in range(20)])
        with self.assertRaises(ValueError):select_entries(p,ids,pd.DataFrame({'Top 1%':range(20)}),20)
