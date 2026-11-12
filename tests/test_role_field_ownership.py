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
        result,report=calibrate_role_ownership(field,bad,slots,target=12000)
        self.assertTrue(result.Captain.eq('A').all())
        self.assertFalse(result[slots[1:]].eq('A').any().any())
        self.assertAlmostEqual(report['Eligible special target %'].sum(),100)
        self.assertAlmostEqual(report['Eligible FLEX target %'].sum(),500)
        self.assertTrue((report['Eligible special target %']+report['Eligible FLEX target %']<=100.00001).all())
        self.assertGreater(result.attrs['role_ownership_calibration']['eligibility_adjustment_max_pp'],0)
    def test_eligibility_adjustment_cannot_invent_zero_role_support(self):
        pool,field,slots=self.fixture()
        pool['Projected CPT Own %']=[100.]+[0.]*7
        pool['Projected Flex Ownership']=[100.]*5+[0.]*3
        with self.assertRaisesRegex(ValueError,'no feasible'):
            calibrate_role_ownership(field,pool,slots)

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
    def test_missing_role_is_rebuilt_using_final_targets_and_verified_salaries(self):
        pool,field,slots=self.fixture()
        pool.loc[0,'Name']='Malik Nabers'
        field=field.replace('A','Malik Nabers')
        selected=field[field.Captain!='Malik Nabers'].copy()
        with self.assertRaisesRegex(ValueError,'Malik Nabers'):
            calibrate_role_ownership(selected,pool,slots)
        result,report=calibrate_role_ownership(selected,pool,slots,target=12000,support_salary_cap=50000)
        self.assertTrue(result.Captain.eq('Malik Nabers').any())
        self.assertTrue(result.Salary.le(50000).all())
        self.assertEqual(len(result),12000)
        self.assertLess(result.attrs['role_ownership_calibration']['final_max_error_pp'],.5)
        self.assertGreater(result.attrs['role_ownership_calibration']['repair_proposal_rosters'],0)

    def test_repair_survives_zero_role_pruning(self):
        pool,field,slots=self.fixture()
        legal=field[~field[slots[1:]].eq('H').any(axis=1)]
        pool['Projected CPT Own %']=[100*legal.Captain.eq(n).mean() for n in pool.Name]
        pool['Projected Flex Ownership']=[100*legal[slots[1:]].eq(n).any(axis=1).mean() for n in pool.Name]
        forbidden=field[field[slots[1:]].eq('H').any(axis=1)]
        result,_=calibrate_role_ownership(forbidden,pool,slots,target=12000,support_salary_cap=50000)
        self.assertFalse(result[slots[1:]].eq('H').any().any())
        self.assertLess(result.attrs['role_ownership_calibration']['final_max_error_pp'],.5)

    def test_contest_downsampling_restores_role_support_before_fit(self):
        pool,field,slots=self.fixture()
        selected=expand_field(field,20)
        # Simulate a role lost when proposals are reduced to contest capacity.
        selected=selected[selected.Captain!='H'].copy()
        restored=restore_role_support(selected,field,pool,slots)
        self.assertTrue(restored.Captain.eq('H').any())
        # Use full support to verify calibration keeps the requested final count.
        restored=restore_role_support(field[field.Captain!='H'],field,pool,slots)
        result,_=calibrate_role_ownership(restored,pool,slots,target=12000)
        self.assertEqual(len(result),12000)
        import ast
        from pathlib import Path
        tree=ast.parse(Path('dfs_app.py').read_text())
        fit=next(node for node in ast.walk(tree) if isinstance(node,ast.Call)
                 and isinstance(node.func,ast.Name) and node.func.id=='calibrate_role_ownership'
                 and any(isinstance(arg,ast.Name) and arg.id=='contest_field_df' for arg in node.args))
        self.assertTrue(any(k.arg=='target' and isinstance(k.value,ast.Name)
                            and k.value.id=='full_opponent_count' for k in fit.keywords))
        restores=[node for node in ast.walk(tree) if isinstance(node,ast.Call)
                  and isinstance(node.func,ast.Name) and node.func.id=='restore_role_support'
                  and any(isinstance(arg,ast.Name) and arg.id=='contest_field_sample_df' for arg in node.args)]
        self.assertTrue(any(node.lineno<fit.lineno for node in restores))

    def test_proposal_support_does_not_require_every_roster_in_final_field(self):
        pool,_,slots=self.fixture();pool['Projected CPT Own %']=[99.999]+[.001/7]*7
        field=build_unique_field(pool,np.ones(8),pool['Projected CPT Own %'],40,min_salary=0,ensure_role_support=True)
        self.assertEqual(set(field.Captain),set(pool.Name))
        self.assertEqual(len(field),40)

if __name__=='__main__':unittest.main()
