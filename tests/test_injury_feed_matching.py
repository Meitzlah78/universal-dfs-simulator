import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
class FeedTests(unittest.TestCase):
    def load(self,payload):
        tree=ast.parse(Path('dfs_app.py').read_text());names={'normalize_injury_player_name','normalize_injury_team','fetch_nfl_injury_statuses'}
        nodes=[]
        for n in tree.body:
            if isinstance(n,ast.FunctionDef) and n.name in names:
                n.decorator_list=[];nodes.append(n)
        response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
        ns={'requests':SimpleNamespace(get=lambda *a,**k:response)}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'injury','exec'),ns)
        return ns
    def test_actual_espn_top_level_team_matches_slate(self):
        ns=self.load({'injuries':[{'displayName':'San Francisco 49ers','injuries':[{'status':'Questionable','athlete':{'displayName':'Mike Evans'}}]},{'displayName':'Washington Commanders','injuries':[{'status':'Doubtful','athlete':{'displayName':'Test Player'}}]}]})
        statuses,_=ns['fetch_nfl_injury_statuses']()
        self.assertEqual(statuses[('mikeevans','SF')],'Questionable')
        self.assertEqual(statuses[('testplayer','WAS')],'Doubtful')
        self.assertEqual(ns['normalize_injury_team']('WSH'),'WAS')
    def test_nested_team_shape_still_works(self):
        ns=self.load({'injuries':[{'team':{'abbreviation':'DAL'},'injuries':[{'status':'Out','athlete':{'fullName':'Example Player'}}]}]})
        self.assertEqual(ns['fetch_nfl_injury_statuses']()[0][('exampleplayer','DAL')],'Out')
