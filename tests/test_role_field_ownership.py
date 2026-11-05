import unittest
import numpy as np
import pandas as pd
from simmah_showdown_field import build_unique_field, expand_field, SLOTS
from simmah_role_field_ownership import calibrate_role_ownership, restore_role_support

class RoleOwnershipTests(unittest.TestCase):
    def fixture(self, fd=False):
        pool=pd.DataFrame({'Name':list('ABCDEFGH'),'Team':['A']*4+['B']*4,'Salary':[5000]*8,'CaptainSalary':[7500]*8})
        field=build_unique_field(pool,np.ones(8),np.ones(8),10000,min_salary=0)
        probability=np.exp(field.Captain.eq('A')*1.2 + field[SLOTS[1:]].eq('B').any(axis=1)*.7)
        probability=np.asarray(probability)/sum(probability)
        pool['Projected CPT Own %']=[100*probability[field.Captain.eq(n)].sum() for n in pool.Name]
        pool['Projected Flex Ownership']=[100*probability[field[SLOTS[1:]].eq(n).any(axis=1)].sum() for n in pool.Name]
        slots=SLOTS
        if fd:
            pool=pool.rename(columns={'Projected CPT Own %':'Projected MVP Ownership'})
            slots=['MVP']+['FLEX'+str(i) for i in range(1,6)]
            field=field.rename(columns=dict(zip(SLOTS,slots)))
        return pool,field,slots
    def test_dk_and_fd_fit_roles_and_preserve_legal_rosters(self):
        for fd in [False,True]:
            pool,field,slots=self.fixture(fd);before=pool.copy(deep=True)
            result,report=calibrate_role_ownership(field,pool,slots,target=12000)
            self.assertEqual(len(result),12000)
            self.assertLess(result.attrs['role_ownership_calibration']['final_max_error_pp'],.2)
            self.assertTrue(result.Salary.eq(32500).all())
            self.assertTrue(all(len(set(r))==6 for r in result[slots].itertuples(index=False,name=None)))
            self.assertLess(len(result.drop_duplicates(slots)),len(result))
            pd.testing.assert_frame_equal(pool,before)
            again,_=calibrate_role_ownership(field,pool,slots,target=12000)
            pd.testing.assert_frame_equal(result,again)
    def test_raw_inputs_preserved_and_eligible_normalization_reported(self):
        pool,field,slots=self.fixture();pool['Projected Flex Ownership']*=.99
        result,report=calibrate_role_ownership(field,pool,slots,target=12000)
        self.assertAlmostEqual(report['Raw FLEX own %'].sum(),495)
        self.assertAlmostEqual(report['Eligible FLEX target %'].sum(),500)
        self.assertAlmostEqual(result.attrs['role_ownership_calibration']['raw_eligible_role_totals'][1],495)
    def test_missing_or_impossible_role_targets_block(self):
        pool,field,slots=self.fixture();bad=pool.copy();bad.loc[0,'Projected CPT Own %']=np.nan
        with self.assertRaisesRegex(ValueError,'Complete'):calibrate_role_ownership(field,bad,slots)
        with self.assertRaisesRegex(ValueError,'support'):calibrate_role_ownership(field[field.Captain!='A'],pool,slots)
        bad=pool.copy();bad['Projected CPT Own %']=0.;bad.loc[0,'Projected CPT Own %']=100
        with self.assertRaisesRegex(ValueError,'more than once'):calibrate_role_ownership(field,bad,slots)
    def test_jointly_infeasible_support_is_rejected(self):
        pool,field,slots=self.fixture()
        field=field[field[slots].isin(list('ABCD')).sum(axis=1)<=3]
        pool['Projected CPT Own %']=12.5
        pool['Projected Flex Ownership']=[85.]*4+[40.]*4
        with self.assertRaisesRegex(ValueError,'could not be matched'):
            calibrate_role_ownership(field,pool,slots,target=12000)
    def test_posted_zero_is_not_invented(self):
        pool,field,slots=self.fixture();field=field[field.Captain!='H'].copy()
        # Derive a feasible target containing no H at Captain.
        pool['Projected CPT Own %']=[100*field.Captain.eq(n).mean() for n in pool.Name]
        pool['Projected Flex Ownership']=[100*field[slots[1:]].eq(n).any(axis=1).mean() for n in pool.Name]
        result,_=calibrate_role_ownership(field,pool,slots,target=10000)
        self.assertFalse(result.Captain.eq('H').any())
    def test_learned_selection_cannot_remove_rare_role_support(self):
        pool,field,slots=self.fixture();selected=field[field.Captain!='H'].copy()
        restored=restore_role_support(selected,field,pool,slots)
        self.assertTrue(restored.Captain.eq('H').any())
        self.assertEqual(len(restored),len(selected)+1)
    def test_proposal_support_does_not_require_every_roster_in_final_field(self):
        pool,_,slots=self.fixture();pool['Projected CPT Own %']=[99.999]+[.001/7]*7
        field=build_unique_field(pool,np.ones(8),pool['Projected CPT Own %'],40,min_salary=0,ensure_role_support=True)
        self.assertEqual(set(field.Captain),set(pool.Name))
        self.assertEqual(len(field),40)

if __name__=='__main__':unittest.main()
