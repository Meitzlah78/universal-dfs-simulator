import unittest
import pandas as pd
import numpy as np
from simmah_nba_pool_overrides import requested_pool_exclusions


class RequestedExclusionTests(unittest.TestCase):
    def setUp(self):
        self.pool=pd.DataFrame([
            {'Player ID':'fd-sergio','Name':'Sergio De Larrea','Team':'DAL','Opponent':'IND','Projected Minutes':None,'Eligible':True},
            {'Player ID':'fd-other','Name':'Another Player','Team':'DAL','Opponent':'IND','Projected Minutes':33,'Eligible':True},
            {'Player ID':'other-team','Name':'Sergio De Larrea','Team':'IND','Opponent':'DAL','Projected Minutes':12,'Eligible':True}])

    def test_explicit_player_drop_preserves_other_players_and_original(self):
        old=self.pool.copy(deep=True)
        result,names=requested_pool_exclusions(self.pool,'2026-10-23','FanDuel')
        self.assertEqual(result['Player ID'].tolist(),self.pool['Player ID'].tolist())
        self.assertEqual(names,['Sergio De Larrea'])
        pd.testing.assert_frame_equal(self.pool,old)
        self.assertEqual(result['Projected Minutes'].tolist(),[7,33,12])
        self.assertEqual(result['Eligible'].tolist(),[False,True,True])
        self.assertEqual(result['User Excluded'].tolist(),[True,False,False])
        self.assertIn('saved DraftKings snapshot',result.loc[0,'Minutes Source'])

    def test_exclusion_is_limited_to_requested_date_and_platform(self):
        for day,platform in [('2026-10-24','FanDuel'),('2026-10-23','DraftKings')]:
            result,names=requested_pool_exclusions(self.pool,day,platform)
            self.assertEqual(names,[])
            pd.testing.assert_frame_equal(self.pool,result)

    def test_fresh_minutes_not_overwritten_and_wrong_game_never_borrowed(self):
        pool=self.pool.copy();pool.loc[0,'Projected Minutes']=8
        result,_=requested_pool_exclusions(pool,'2026-10-23','FanDuel')
        self.assertEqual(result.loc[0,'Projected Minutes'],8)
        pool=self.pool.copy();pool.loc[0,'Opponent']='HOU'
        result,_=requested_pool_exclusions(pool,'2026-10-23','FanDuel')
        self.assertTrue(pd.isna(result.loc[0,'Projected Minutes']))
        self.assertFalse(result.loc[0,'Eligible'])

    def test_excluded_player_remains_in_complete_team_simulation(self):
        from simmah_nba_pregame import PregameEngine,ROLE_COLUMNS
        from simmah_nba_engine import EventRates
        rows=[dict(self.pool.iloc[0],Projection=7.5,**{c:1 for c in ROLE_COLUMNS})]
        for i,minutes in enumerate([47,47,47,46,46]):
            rows.append(dict(self.pool.iloc[1],**{'Player ID':'dal'+str(i),'Projection':30,
                         'Projected Minutes':minutes,**{c:1 for c in ROLE_COLUMNS}}))
        for i in range(5):
            rows.append(dict(self.pool.iloc[2],**{'Player ID':'ind'+str(i),'Name':'IND '+str(i),
                         'Projection':30,'Projected Minutes':48,**{c:1 for c in ROLE_COLUMNS}}))
        pool=pd.DataFrame(rows);pool['Injury Status']='Active'
        result,_=requested_pool_exclusions(pool,'2026-10-23','FanDuel')
        self.assertFalse(result.loc[0,'Eligible'])
        self.assertEqual(result[result.Team=='DAL']['Projected Minutes'].sum(),240)
        rates=EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)
        engine=PregameEngine(result,[],rates,parallel=False)
        output=engine(4,7)
        self.assertEqual(output.shape,(4,len(result)))
        self.assertTrue(np.isfinite(output).all())

    def test_excluded_player_never_enters_candidates_or_opponent_support(self):
        from simmah_nba_candidates import build_candidates,build_opponent_support
        rows=[]
        for i in range(14):
            team=['DAL','IND','NY','BOS'][i%4]
            rows.append({'Player ID':str(i),'Name':'Sergio De Larrea' if i==0 else 'Player '+str(i),
                         'Team':team,'Opponent':{'DAL':'IND','IND':'DAL','NY':'BOS','BOS':'NY'}[team],
                         'Position':'PG/SG/SF/PF/C','Salary':4000,'Projection':30,
                         'Projected Minutes':None if i==0 else 20,'Eligible':True,'Injury Status':'Active'})
        result,_=requested_pool_exclusions(pd.DataFrame(rows),'2026-10-23','FanDuel')
        outcomes=np.random.default_rng(761).uniform(10,70,(30,len(result)))
        candidates=build_candidates(result,outcomes,target=10)
        opponents=build_opponent_support(result,outcomes,np.full(len(result),25.),target=10)
        self.assertFalse((candidates['indices']==0).any())
        self.assertFalse((opponents['indices']==0).any())
