import unittest
import numpy as np
import pandas as pd
from simmah_nba_markets import implied_scores,extract_markets,simulate_market_game
from simmah_nba_engine import EventRates

class MarketTests(unittest.TestCase):
    def test_spread_sign_and_two_sided_validation(self):
        self.assertEqual(implied_scores(230,-10),(120,110))
        pool=pd.DataFrame({'Team':['NYK','PHI'],'Opponent':['PHI','NY'],
                           'Game Total':[230,230],'Team Implied Points':[120,110]})
        m=extract_markets(pool)[0]
        self.assertEqual(m['teams'],('NY','PHI'))
        self.assertEqual(m['team_0_spread'],-10)
        pool.loc[1,'Team Implied Points']=115
        self.assertEqual(extract_markets(pool),[])
    def test_event_calibration_moves_toward_distinct_targets(self):
        rotation=np.broadcast_to(np.arange(10).reshape(1,2,1,5),(2000,2,48,5)).copy()
        rates=[EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)]*2
        result=simulate_market_game(rotation,np.ones((2,5,5)),rates,[100,125],37)
        report=result['market_calibration']
        self.assertTrue(report['within_four_points'],report)
        s=result['stats'];points=2*s[:,:,0]+s[:,:,1]+s[:,:,2]
        np.testing.assert_array_equal(points[:,:5].sum(axis=1),result['team_points'][:,0])
        self.assertEqual(rates[0].make_two,.53)
    def test_bad_market_rejected(self):
        with self.assertRaises(ValueError):implied_scores(float('nan'),2)
        with self.assertRaises(ValueError):simulate_market_game(None,None,None,[0,100],1)
