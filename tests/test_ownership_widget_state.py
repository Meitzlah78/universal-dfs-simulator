"""Exercise the ownership report UI with Streamlit's widget-state restriction."""
import ast
from contextlib import nullcontext
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd


class GuardedState(dict):
    def __init__(self, widgets):
        super().__init__()
        self.widgets=widgets

    def __setitem__(self,key,value):
        if key in self.widgets:
            raise RuntimeError('Cannot assign an instantiated widget key')
        super().__setitem__(key,value)


class StreamlitStub:
    def __init__(self):
        self.widgets=set()
        self.session_state=GuardedState(self.widgets)

    def download_button(self,*args,key,**kwargs):
        self.widgets.add(key)

    def spinner(self,*args,**kwargs):return nullcontext()
    def expander(self,*args,**kwargs):return nullcontext()
    def caption(self,*args,**kwargs):pass
    def warning(self,*args,**kwargs):pass
    def dataframe(self,*args,**kwargs):pass


class OwnershipWidgetStateTests(unittest.TestCase):
    def test_report_storage_never_writes_to_download_widget_for_either_site(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='apply_learned_field')
        field=pd.DataFrame({'Salary':[60000]})
        report=pd.DataFrame({'Name':['Example'],'Projected Ownership':[20.]})
        st=StreamlitStub()
        env={'st':st,'learned_field_profiles':lambda *args:[],
             'calibrate_field':lambda *args:(field.copy(),{'applied':False,'reason':'Fixture'})}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<ownership-ui>','exec'),env)
        with patch('simmah_field_ownership.has_ownership_targets',return_value=True),patch('simmah_field_ownership.calibrate_field_ownership',return_value=(field.copy(),report)):
            for site,mode in [('FanDuel','Full Roster'),('DraftKings','Classic')]:
                # Repeat on a rerun with the existing report in session state.
                for _ in range(2):
                    env[fn.name](field,pd.DataFrame(),[],site,mode,{},1,np.random.default_rng(1))
                key=f'ownership_comparison_data_{site}_{mode}'
                pd.testing.assert_frame_equal(st.session_state[key],report)
                self.assertIn(f'ownership_comparison_download_{site}_{mode}',st.widgets)
                self.assertNotIn(key,st.widgets)

if __name__=='__main__':unittest.main()
