import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import unittest
import pandas as pd
class MarketDisplayTests(unittest.TestCase):
    def test_saved_report_renders_on_each_rerun_and_rejects_other_pool(self):
        tree=ast.parse(Path('dfs_app.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_saved_market_calibration')
        downloads=[];shown=[]
        st=SimpleNamespace(session_state={'simulation_preparation_FanDuel':{'input_players':[{'Name':'A'}],'market_report':[{'Team':'SF','Market target':30,'Pilot mean':29.5}]}},expander=lambda *a,**k:nullcontext(),caption=lambda *a:None,dataframe=lambda r,**k:shown.append(r),download_button=lambda *a,**k:downloads.append(a))
        ns={'st':st,'pd':pd};exec(compile(ast.Module(body=[node],type_ignores=[]),'report','exec'),ns)
        for _ in range(2):ns[node.name]('FanDuel','Single Game',pd.DataFrame({'Name':['A']}))
        self.assertEqual(len(downloads),2);self.assertIn(b'Market target',downloads[0][1])
        ns[node.name]('FanDuel','Single Game',pd.DataFrame({'Name':['B']}));self.assertEqual(len(shown),2)
