import unittest
from unittest.mock import patch
import numpy as np
from simmah_nba_overtime_rotations import OvertimeRotations
from simmah_nba_rotation_schedule import build_rotation
from simmah_nba_engine import simulate_game,EventRates


class OvertimeRotationTests(unittest.TestCase):
    def minutes(self):return np.tile([4,4,4,4,3,3,3],(2,1)).astype(float)

    def eager(self,minutes,n,seeds,periods):
        return np.stack([np.stack([build_rotation(np.tile(minutes[t],(n,1)),
            seeds[t]+p*11,t*minutes.shape[1],period_minutes=5)
            for p in range(periods)],axis=1) for t in (0,1)],axis=1)

    def test_exact_seeded_tensor_and_prefix_pilot(self):
        m=self.minutes();seeds=[41,42];ot=OvertimeRotations(m,128,seeds,10)
        self.assertEqual(len(ot._cache),0)
        expected=self.eager(m,128,seeds,10)
        np.testing.assert_array_equal(ot.materialize(),expected)
        np.testing.assert_array_equal(ot[:17].materialize(),expected[:17])
        ids=np.array([0,16,4]);periods=np.array([0,9,3]);minutes=np.array([0,4,2])
        np.testing.assert_array_equal(ot[:17][ids,1,periods,minutes],expected[ids,1,periods,minutes])

    def test_only_requested_periods_are_allocated_and_prefix_shares_cache(self):
        ot=OvertimeRotations(self.minutes(),128,[41,42],10);view=ot[:17]
        with patch('simmah_nba_overtime_rotations.build_rotation',wraps=build_rotation) as build:
            view[np.array([0]),0,np.array([2]),np.array([4])]
            self.assertEqual(build.call_count,2)
            ot[np.array([127]),1,np.array([2]),np.array([0])]
            self.assertEqual(build.call_count,2)
        self.assertEqual(set(ot._cache),{2})

    def test_event_ledgers_scores_and_all_ten_overtimes_are_identical(self):
        n=24;m=self.minutes();size=m.shape[1]
        reg=np.tile(np.arange(5),(n,2,48,1));reg[:,1]+=size
        profiles=np.ones((2,size,5))
        # Every action is a turnover: regulation and all ten OT periods tie.
        rates=[EventRates(1,0,0,0,0,0,0,0,0,0,13)]*2
        lazy=OvertimeRotations(m,n,[51,52],10)
        expected=simulate_game(reg,profiles,rates,70,self.eager(m,n,[51,52],10))
        actual=simulate_game(reg,profiles,rates,70,lazy)
        for key in ['scores','stats','team_points','requires_overtime','overtime_periods','elapsed_seconds']:
            np.testing.assert_array_equal(actual[key],expected[key])
        for key in actual['counters']:np.testing.assert_array_equal(actual['counters'][key],expected['counters'][key])
        self.assertTrue((actual['overtime_periods']==10).all())
        self.assertEqual(len(lazy._cache),10)

    def test_reject_bad_minutes_shape_and_event_indices(self):
        for m in [np.ones((2,7)),np.full((2,5),6),np.ones((1,25)),np.full((2,5),np.nan)]:
            with self.assertRaises(ValueError):OvertimeRotations(m,10,[1,2],10)
        ot=OvertimeRotations(self.minutes(),10,[1,2],10)
        with self.assertRaises(IndexError):ot[2:]
        with self.assertRaises(IndexError):ot[np.array([10]),0,np.array([0]),np.array([0])]

    def test_pregame_market_fit_and_independent_sets_match_eager(self):
        from test_nba_build_contract import fixture
        from simmah_nba_pregame import PregameEngine
        from simmah_nba_overtime_rotations import OvertimeRotations as Original
        _,pool,rates=fixture()
        markets=[{'teams':('DAL','IND'),'implied_points':(110.,112.)}]
        class Eager:
            def __new__(cls,*args,**kwargs):return Original(*args,**kwargs).materialize()
        for platform in ('DraftKings','FanDuel'):
            pool.attrs.update(nba_variable_minutes=True,nba_wider_minutes=True)
            old=PregameEngine(pool,markets,rates,parallel=False,platform=platform)
            new=PregameEngine(pool,markets,rates,parallel=False,platform=platform)
            for seed in [83,1092,2100]:
                with patch('simmah_nba_overtime_rotations.OvertimeRotations',Eager):expected=old(64,seed)
                actual=new(64,seed)
                np.testing.assert_array_equal(actual,expected)
                self.assertEqual(new.last_report,old.last_report)
