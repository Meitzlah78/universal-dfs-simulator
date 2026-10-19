import ast,unittest
from pathlib import Path
import numpy as np,pandas as pd
from simmah_showdown_field import build_unique_field,expand_field,SLOTS

class ShowdownFieldTests(unittest.TestCase):
    def pool(self):
        p=pd.DataFrame({'Name':list('ABCDEFGH'),'Team':['A']*4+['B']*4,'Salary':[5000]*8})
        p['CaptainSalary']=7500;return p
    def test_exact_legal_count_and_unique_sample(self):
        p=self.pool();f=build_unique_field(p,np.ones(8),np.ones(8),100,min_salary=0)
        self.assertEqual(len(f),100);self.assertEqual(len(f.drop_duplicates(SLOTS)),100)
        self.assertEqual(f.attrs['legal_combinations'],168)
        for row in f[SLOTS].itertuples(index=False,name=None):self.assertEqual(len(set(row)),6)
        self.assertTrue(f.Salary.eq(32500).all())
    def test_unavailable_count_is_explicit_not_duplicate_filled(self):
        p=self.pool();f=build_unique_field(p,np.ones(8),np.ones(8),10000,min_salary=0)
        self.assertEqual(len(f),168);self.assertEqual(f.attrs['requested_unique'],10000)
    def test_captain_assignment_is_part_of_identity(self):
        p=self.pool();f=build_unique_field(p,np.ones(8),np.ones(8),10000,min_salary=0)
        ordinary={tuple(sorted(row)) for row in f[SLOTS].itertuples(index=False,name=None)}
        self.assertEqual(len(ordinary),28)
    def test_expansion_preserves_unique_support_without_chalk_amplification(self):
        p=self.pool();f=build_unique_field(p,np.ones(8),np.ones(8),100,min_salary=0)
        e=expand_field(f,20000)
        self.assertEqual(len(e),20000);self.assertEqual(len(e.drop_duplicates(SLOTS)),100)
        freq=e.groupby(SLOTS).size();self.assertLess(freq.max(),270);self.assertGreater(freq.min(),140)
    def test_app_captain_input_has_no_generated_field_feedback(self):
        tree=ast.parse(Path('dfs_app.py').read_text());n=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_showdown_opponent_field')
        values={n.value for n in ast.walk(n) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        self.assertNotIn('field cpt own %',values);self.assertIn('projected cpt own %',values)
    def test_app_builder_ignores_prior_field_captain_output(self):
        from types import SimpleNamespace
        tree=ast.parse(Path('dfs_app.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_showdown_opponent_field')
        ns={'pd':pd,'np':np,'st':SimpleNamespace(session_state={}),
            'opponent_field_selection_weights':lambda p,m:np.ones(len(p)),
            'learned_field_proposal_target':lambda *a:a[4],
            'apply_learned_field':lambda field,*a:field.head(a[-2]).copy()}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'dfs_app.py','exec'),ns)
        p=self.pool();p['Salary']=7500;p['Projection']=np.arange(8)+1
        salary=dict(zip(p.Name,p.Salary));captain={n:v*1.5 for n,v in salary.items()}
        sim=pd.DataFrame([np.ones(8)],columns=p.Name)
        p['Field CPT Own %']=0.;p.loc[0,'Field CPT Own %']=100.
        first=ns['build_showdown_opponent_field'](p.Name,sim,p,salary,captain,50000,100)
        p['Field CPT Own %']=100.
        second=ns['build_showdown_opponent_field'](p.Name,sim,p,salary,captain,50000,100)
        pd.testing.assert_frame_equal(first,second)
        self.assertEqual(len(first),100)

    def test_pasted_payouts_reconcile_and_stay_scoped(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        value=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_was_sf_ranges' for t in n.targets))
        ranges=ast.literal_eval(value)
        self.assertEqual(max(b for a,b,v in ranges),14240)
        self.assertAlmostEqual(sum((b-a+1)*v for a,b,v in ranges),5000)

if __name__=='__main__':unittest.main()
