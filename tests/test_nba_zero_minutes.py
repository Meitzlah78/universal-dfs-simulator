import unittest
import numpy as np
import pandas as pd
from simmah_nba_projections import parse_rotowire
from simmah_nba_pregame import PregameEngine, ROLE_COLUMNS
from simmah_nba_engine import EventRates

class ZeroMinuteRotationTests(unittest.TestCase):
    def test_parser_distinguishes_zero_from_missing(self):
        pool=pd.DataFrame([{'Team':'ATL','Opponent':'ORL'}])
        base={'slateID':1,'firstName':'Reserve','lastName':'Player','team':{'abbr':'ATL'},'opponent':{'team':'ORL'},'game':{'dateTime':'2026-10-21 19:00:00'}}
        proj={'access':True,'source':'RotoWire','projections':[{'slateID':1,'pts':5}]}
        for value,expected in [(0,0),(None,None),(-1,None),(float('nan'),None),(49,None)]:
            _,details=parse_rotowire([{**base,'minutes':value}],proj,'2026-10-21',pool)
            row=details[('reserve player','ATL')]
            self.assertEqual(row['Projected Minutes'],expected)
            self.assertEqual(row['Minutes Source'],'RotoWire' if expected is not None else 'Missing')

    def test_complete_rotation_allows_zero_minute_positive_projection_reserve(self):
        pool=pd.DataFrame([{'Player ID':str(i),'Team':'ATL' if i<5 else 'ORL',
            'Opponent':'ORL' if i<5 else 'ATL','Projection':30,'Injury Status':'Active',
            'Projected Minutes':48,**{c:1 for c in ROLE_COLUMNS}} for i in range(10)])
        reserve={**pool.iloc[0].to_dict(),'Player ID':'reserve','Projected Minutes':0}
        pool=pd.concat([pool,pd.DataFrame([reserve])],ignore_index=True)
        markets=[{'teams':('ATL','ORL'),'implied_points':(110,110)}]
        rates=EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)
        engine=PregameEngine(pool,markets,rates)
        self.assertEqual(len(engine.games[0][1][0][0]),5)
        self.assertEqual(sum(engine.games[0][1][0][1]),240)
        pool.loc[10,'Projected Minutes']=np.nan
        with self.assertRaisesRegex(ValueError,'Complete positive projected rotation'):PregameEngine(pool,markets,rates)
        pool.loc[10,'Projected Minutes']=0
        pool.loc[0,'Projected Minutes']=47
        with self.assertRaisesRegex(ValueError,'240 required'):PregameEngine(pool,markets,rates)
