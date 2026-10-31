import unittest
import pandas as pd
from simmah_nba_reconciliation import reconcile_minutes

class ReconciliationTests(unittest.TestCase):
    def frames(self):
        pre=pd.DataFrame({'Game ID':['1','1'],'NBA Player ID':['10','11'],'Team':['A','A'],
            'GameStart':['2026-10-20T23:00Z']*2,'CapturedAt':['2026-10-20T22:00Z']*2,'Projected Minutes':[30,20]})
        actual=pd.DataFrame({'Game ID':['1','1'],'NBA Player ID':['10','12'],'Team':['A','A'],
            'Actual Minutes':[None,10.],'Status':['dnp','played'],'Final':[True,True],'Overtimes':[0,0]})
        return pre,actual
    def test_missing_is_not_zero_and_unexpected_has_no_invented_forecast(self):
        pre,actual=self.frames();r=reconcile_minutes(pre,actual)
        self.assertEqual(r['verified_dnp'],1)
        self.assertEqual(r['coverage'],{'matched':1,'missing_actual':1,'missing_pregame':1})
        self.assertEqual(r['metrics']['regulation']['mae'],30)
        self.assertFalse(r['team_ledgers'][0]['ledger_reconciled'])
        unexpected=r['rows'].query('Reconciliation == "missing_pregame"').iloc[0]
        self.assertTrue(pd.isna(unexpected['Projected Minutes']))
    def test_overtime_reported_separately_and_bad_inputs_rejected(self):
        pre,actual=self.frames();actual['Overtimes']=1
        r=reconcile_minutes(pre,actual)
        self.assertEqual(r['metrics']['regulation']['players'],0)
        self.assertEqual(r['metrics']['overtime_full_game']['players'],1)
        for column,value in [('Overtimes',None),('Final',False),('Team','B')]:
            broken=actual.copy();broken.loc[0,column]=value
            with self.assertRaises(ValueError):reconcile_minutes(pre,broken)
        pre.loc[0,'CapturedAt']='2026-10-21T00:00Z'
        with self.assertRaises(ValueError):reconcile_minutes(pre,actual)
