import itertools,unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import pandas as pd
from simmah_selector_budget import select_quality_budget,CapConflict,QualityNotCertified


def fixture():
    return pd.DataFrame([['A','B',.10],['A','C',.09],['G','H',.085],['E','F',.08],['I','J',.075]],columns=['X','Y','Top1'])


class BudgetTests(unittest.TestCase):
    def test_certified_optimum_and_diversity_match_enumeration(self):
        c=fixture();s=select_quality_budget(c,['X','Y'],3,automatic_max=66.67)
        feasible=[]
        for ids in itertools.combinations(range(len(c)),3):
            rows=c.iloc[list(ids)];cnt=pd.Series(rows[['X','Y']].values.ravel()).value_counts()
            if cnt.max()<=2:feasible.append((rows.Top1.sum(),(cnt**2).sum()))
        optimum=max(q for q,k in feasible);best=min(k for q,k in feasible if q>=.95*optimum)
        self.assertAlmostEqual(s.attrs['quality_optimum'],optimum)
        self.assertEqual(s.attrs['concentration_after'],best)
        self.assertLessEqual(s.attrs['actual_quality_loss'],.05+1e-9)
    def test_zero_budget_preserves_optimum(self):
        s=select_quality_budget(fixture(),['X','Y'],3,automatic_max=66.67,quality_loss=0)
        self.assertAlmostEqual(s.Top1.sum(),s.attrs['quality_optimum'])
    def test_infeasible_caps_never_relax(self):
        c=fixture();c['X']='Always'
        with self.assertRaises(CapConflict):select_quality_budget(c,['X','Y'],3,automatic_max=80)
        with self.assertRaises(CapConflict):select_quality_budget(fixture(),['X','Y'],3,controls={'Absent':{'Min Exposure %':10}})
        with self.assertRaises(CapConflict):select_quality_budget(fixture(),['X','Y'],3,controls={'A':{'Lock':True}},automatic_max=80)
    def test_role_caps_and_fades(self):
        c=fixture().rename(columns={'X':'Captain','Y':'Flex1'})
        s=select_quality_budget(c,['Captain','Flex1'],3,automatic_max=100,
            controls={'A':{'Captain Max %':34},'I':{'Fade':True}})
        self.assertLessEqual(s.Captain.eq('A').sum(),1)
        self.assertFalse(s[['Captain','Flex1']].eq('I').any().any())
    def test_duplicates_are_not_extra_support(self):
        c=pd.concat([fixture().iloc[:1]]*4,ignore_index=True)
        with self.assertRaises(CapConflict):select_quality_budget(c,['X','Y'],2)
    def test_quality_timeout_is_not_certified(self):
        with patch('simmah_selector_budget.milp',return_value=SimpleNamespace(status=1,x=None)):
            with self.assertRaises(QualityNotCertified):select_quality_budget(fixture(),['X','Y'],3)
    def test_second_stage_timeout_returns_certified_optimum(self):
        from simmah_selector_budget import milp
        calls=[]
        def solve(*args,**kwargs):
            calls.append(1)
            return milp(*args,**kwargs) if len(calls)==1 else SimpleNamespace(status=1,x=None)
        with patch('simmah_selector_budget.milp',side_effect=solve):s=select_quality_budget(fixture(),['X','Y'],3)
        self.assertEqual(s.attrs['actual_quality_loss'],0)
        self.assertFalse(s.attrs['diversity_optimal'])
    def test_future_results_do_not_affect_selection(self):
        c=fixture();a=select_quality_budget(c,['X','Y'],3)
        c['Actual']=np.arange(len(c))*999;c['Prize']=10000-c.Actual
        b=select_quality_budget(c,['X','Y'],3)
        self.assertEqual(set(map(tuple,a[['X','Y']].values)),set(map(tuple,b[['X','Y']].values)))
    def test_dk_classic_and_fd_full_roster(self):
        for defense in ['DST','DEF']:
            slots=['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX',defense]
            rows=[]
            for i,q in enumerate([.10,.095,.09,.085]):
                row={slot:f'{slot}-{i}' for slot in slots};row['QB']='shared-QB' if i<2 else f'QB-{i}';row['Top1']=q;rows.append(row)
            s=select_quality_budget(pd.DataFrame(rows),slots,3,automatic_max=80,
                controls={'shared-QB':{'Max Exposure %':34}})
            self.assertEqual(len(s),3)
            self.assertLessEqual(s.QB.eq('shared-QB').sum(),1)
            self.assertTrue(all(len(set(row))==9 for row in s[slots].values))
            self.assertLessEqual(s.attrs['max_exposure_pct'],80)
            self.assertLessEqual(s.attrs['actual_quality_loss'],.05+1e-9)


if __name__=='__main__':unittest.main()
