"""The app must retain both value-finder and candidate-leverage interfaces."""
import ast
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
import simmah_leverage as leverage

class LeverageAppContractTests(unittest.TestCase):
    def test_every_app_leverage_import_exists(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        imports={a.name for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module=='simmah_leverage' for a in n.names}
        self.assertTrue({'add_value_columns','leverage_report','candidate_opportunities','attach_leverage'}<=imports)
        for name in imports:
            with self.subTest(name=name):self.assertTrue(callable(getattr(leverage,name,None)),name)

    def test_value_metrics_and_invalid_salary(self):
        p=pd.DataFrame({'Name':['A','B','C'],'Position':['WR','WR','RB'],'Salary':[5000,0,4000],'Projection':[15,8,12],'Sim P95':[30,np.nan,24]})
        result=leverage.add_value_columns(p)
        self.assertEqual(result['Projected Pts / $1k'].iloc[0],3.)
        self.assertEqual(result['P95 Pts / $1k'].iloc[0],6.)
        self.assertTrue(pd.isna(result['Projected Pts / $1k'].iloc[1]))
        self.assertNotIn('Projected Pts / $1k',p)

    def test_finder_before_build_keeps_pending_blank(self):
        p=pd.DataFrame({'Name':['A'],'Salary':[5000],'Projection':[15],'Position':['QB']})
        result=leverage.leverage_report(p,None,None,['QB'])
        self.assertEqual(result['Projected Pts / $1k'].iloc[0],3.)
        self.assertTrue(result['Sim Leverage (pp)'].isna().all())

    def test_finder_for_all_four_format_slot_schemas(self):
        for slots,special in [(['Captain','Flex1','Flex2','Flex3','Flex4','Flex5'],'Captain'),(['MVP','Flex1','Flex2','Flex3','Flex4','Flex5'],'MVP'),(['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','DST'],None),(['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','D'],None)]:
            with self.subTest(slots=slots):
                names=list('ABCDEFGHIJ')[:len(slots)+1]
                pool=pd.DataFrame({'Name':names,'Salary':5000,'Projection':10})
                candidates=pd.DataFrame([names[:-1],names[1:]],columns=slots);candidates['Top1']=[.75,.25]
                field=pd.DataFrame([names[1:],names[1:]],columns=slots)
                result=leverage.leverage_report(pool,candidates,field,slots,special).set_index('Name')
                self.assertEqual(result.loc['A','Sim Leverage (pp)'],75.)
                self.assertEqual(result.attrs['field_entries'],2)
                if special:self.assertEqual(result.loc['A','CPT/MVP Weighted Presence %'],75.)

if __name__=='__main__':unittest.main()
