import ast,contextlib,unittest
from pathlib import Path
import numpy as np,pandas as pd
from simmah_opponent_diagnostics import numeric_column,with_roster_projections

class OpponentDiagnosticsTests(unittest.TestCase):
    def fixture(self):
        slots=['MVP']+['FLEX'+str(i) for i in range(1,6)]
        pool=pd.DataFrame({'Name':list('ABCDEFGH'),'Projection':range(1,9)})
        field=pd.DataFrame([dict(zip(slots,['H','A','B','C','D','E']))]);field['Salary']=50000
        return pool,field,slots
    def test_real_mvp_total_and_inputs_unchanged(self):
        pool,field,slots=self.fixture();before=field.copy()
        result=with_roster_projections(field,pool,slots,[1.5,1,1,1,1,1])
        self.assertEqual(result.ProjectedPoints.iloc[0],27)
        pd.testing.assert_frame_equal(field,before)
        pd.testing.assert_frame_equal(result[field.columns],field)
    def test_existing_values_survive_and_unknowns_stay_unknown(self):
        pool,field,slots=self.fixture();field['ProjectedPoints']=40
        self.assertEqual(with_roster_projections(field,pool,slots).ProjectedPoints.iloc[0],40)
        field=field.drop(columns='ProjectedPoints');field.loc[0,'MVP']='Unknown'
        self.assertTrue(with_roster_projections(field,pool,slots).ProjectedPoints.isna().all())
        self.assertTrue(numeric_column(field,'Missing').dropna().empty)
    def test_live_persistent_view_renders_roster_only_saved_field(self):
        pool,field,slots=self.fixture()
        tree=ast.parse(Path('dfs_app.py').read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.If)
            and any(isinstance(s,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_fd_field_proj' for t in s.targets) for s in n.body)
            and '_fd_persist_field' in ast.unparse(n.test))
        class UI:
            def __init__(self):self.session_state={};self.metrics={}
            def expander(self,*a,**kw):return contextlib.nullcontext()
            def container(self,*a,**kw):return contextlib.nullcontext()
            def columns(self,n):return [self]*n
            def metric(self,name,value):self.metrics[name]=value
            def __getattr__(self,name):return lambda *a,**kw:None
        ui=UI();ns={'pd':pd,'np':np,'st':ui,'_fd_persist_field':field,'_fd_field_key':'saved',
            'fd_players':pool,'fd_slots':slots,'lineup_mode':'Single Game','fd_rank_source':field.copy(),
            'numeric_column':numeric_column,'with_roster_projections':with_roster_projections,
            'workspace_download_button':lambda *a,**kw:None,'injury_frame':lambda st,f:f}
        exec(compile(ast.Module(body=node.body,type_ignores=[]),'live-persistent-field','exec'),ns)
        self.assertEqual(ui.metrics['Opponent avg projection'],'27.00')
        self.assertEqual(ui.metrics['My avg projection'],'N/A')
        self.assertEqual(ui.session_state['saved'].ProjectedPoints.iloc[0],27)

if __name__=='__main__':unittest.main()
