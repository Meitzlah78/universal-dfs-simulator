import ast,io,json,unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from simmah_rotowire import select_slate,parse_projections,salary_dates,download,FORMATS

class RotoWireTests(unittest.TestCase):
    def test_download_identifies_json_requests_and_keeps_access_checks(self):
        from urllib.request import Request
        from urllib.parse import urlparse
        calls=[]
        players=[{'slateID':7,'firstName':'Value','lastName':'Player',
                  'team':{'abbr':'WAS'},'game':{'dateTime':'2026-10-19'}}]
        def opener(request,timeout):
            self.assertIsInstance(request,Request)
            self.assertEqual(request.get_header('User-agent'),'Simmah/1.0')
            self.assertEqual(request.get_header('Accept'),'application/json')
            self.assertEqual(timeout,12)
            endpoint=urlparse(request.full_url).path.rsplit('/',1)[-1]
            calls.append(endpoint)
            payload={'slate-list.php':self.slate('Showdown'),'players.php':players,
                     'projections.php':{'access':True,'source':'RotoWire',
                                        'projections':[{'slateID':7,'pts':6.95}]}}[endpoint]
            return io.BytesIO(json.dumps(payload).encode())
        result,sid=download('DraftKings Showdown',['SF','WAS'],['2026-10-19'],opener=opener)
        self.assertEqual(result,{'valueplayer':6.95});self.assertEqual(sid,'1')
        self.assertEqual(calls,['slate-list.php','players.php','projections.php'])

    def slate(self,mode):
        return {'slates':[{'slateID':1,'contestType':mode,'games':[9]}],
            'games':{'9':{'homeTeamCode':'SF','visitTeamCode':'WSH','gameDate':'2026-10-19 20:15:00'}}}
    def test_exact_platform_team_and_date_selection_all_formats(self):
        for platform,(_,mode) in FORMATS.items():
            self.assertEqual(select_slate(self.slate(mode),platform,['SF','WAS'],['2026-10-19'])['slateID'],1)
            for teams,dates in [(['SF','DAL'],['2026-10-19']),(['SF','WAS'],['2026-10-25'])]:
                with self.assertRaises(ValueError):select_slate(self.slate(mode),platform,teams,dates)
    def test_ambiguous_or_wrong_format_rejected(self):
        p=self.slate('Showdown');p['slates']*=2
        with self.assertRaises(ValueError):select_slate(p,'DraftKings Showdown',['SF','WAS'],['2026-10-19'])
        with self.assertRaises(ValueError):select_slate(self.slate('Classic'),'DraftKings Showdown',['SF','WAS'],['2026-10-19'])
    def test_positive_points_only_and_defense_aliases_no_multiplier(self):
        players=[{'slateID':1,'firstName':'Brock','lastName':'Purdy','team':{'abbr':'SF'},'game':{'dateTime':'2026-10-19'}},
            {'slateID':2,'firstName':'Washington','lastName':'Commanders','team':{'abbr':'WAS','nickname':'Commanders'},'isTeamDefense':True,'game':{'dateTime':'2026-10-19'}}]
        payload={'access':True,'source':'RotoWire','projections':[{'slateID':1,'pts':20},{'slateID':2,'pts':4}]}
        result=parse_projections(players,payload,['SF','WAS'],['2026-10-19'])
        self.assertEqual(result['brockpurdy'],20);self.assertEqual(result['commanders'],4)
        payload['projections'][0]['pts']=float('nan')
        self.assertNotIn('brockpurdy',parse_projections(players,payload,['SF','WAS'],['2026-10-19']))
        payload['access']=False
        with self.assertRaises(ValueError):parse_projections(players,payload,['SF','WAS'],['2026-10-19'])
    def test_salary_date_extraction(self):
        p=pd.DataFrame({'Game Info':['WAS@SF 10/19/2026 08:15PM ET']})
        self.assertEqual(salary_dates(p),('2026-10-19',))
        self.assertEqual(salary_dates(pd.DataFrame({'Name':['Player 2026-10-25']})),())
    def app(self,uploads=False):
        tree=ast.parse(Path('dfs_app.py').read_text());n=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='apply_external_projection_sources')
        calls=[]
        def rw(*args):calls.append(args);return {'player':30.,'zero':0.},'123'
        ns={'np':np,'pd':pd,'st':SimpleNamespace(caption=lambda *a:None,session_state={}),
            'ZoneInfo':__import__('zoneinfo').ZoneInfo,
            'get_projection_source_data':lambda file,source,*a:({'player':10. if source=='DFF' else 20.,'zero':0.},'test'),
            'download_rotowire_projections':rw,'normalize_projection_player_name':lambda x:x.lower()}
        exec(compile(ast.Module(body=[n],type_ignores=[]),'app','exec'),ns)
        p=pd.DataFrame({'Name':['Player','Zero'],'Team':['SF','WAS'],'Game Info':['WAS@SF 10/19/2026']*2})
        result=ns[n.name](p,object() if uploads else None,None,'DraftKings Showdown')
        return result,calls
    def test_incomplete_upload_automatically_fills_missing_players_only(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='apply_external_projection_sources')
        calls=[]
        def source(file,label,*args):
            return ({'player':10.,'zero':0.} if label=='DFF' else {}),'test'
        def rw(*args):
            calls.append(args);return {'player':30.,'reserve':6.95,'zero':8.},'123'
        ns={'np':np,'pd':pd,'st':SimpleNamespace(caption=lambda *a:None,session_state={}),
            'ZoneInfo':__import__('zoneinfo').ZoneInfo,'get_projection_source_data':source,
            'download_rotowire_projections':rw,'normalize_projection_player_name':lambda x:x.lower()}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'app','exec'),ns)
        pool=pd.DataFrame({'Name':['Player','Reserve','Zero'],'Team':['SF','WAS','WAS'],
                           'Game Info':['WAS@SF 10/19/2026']*3})
        result=ns[fn.name](pool,object(),None,'DraftKings Showdown')
        self.assertEqual(len(calls),1)
        self.assertEqual(result.Projection.iloc[0],10.)
        self.assertEqual(result.Projection.iloc[1],6.95)
        self.assertEqual(result.ProjectionSource.iloc[1],'RotoWire')
        self.assertTrue(np.isnan(result.Projection.iloc[2]))

    def test_three_source_average_and_missing_zero(self):
        r,c=self.app();self.assertEqual(r.Projection.iloc[0],20.);self.assertTrue(np.isnan(r.Projection.iloc[1]));self.assertEqual(len(c),1)
        self.assertIn('RotoWire',r.ProjectionSource.iloc[0])
    def test_uploaded_priority_skips_rotowire(self):
        r,c=self.app(True);self.assertEqual(r.Projection.iloc[0],15.);self.assertEqual(c,[])

if __name__=='__main__':unittest.main()
