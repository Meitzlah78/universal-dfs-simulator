import unittest
from copy import deepcopy
from dataclasses import replace
import numpy as np
import test_nba_pregame
from simmah_nba_pregame import PregameEngine
from simmah_nba_simulation_cache import CachedNBAOutcomes,clear_simulation_cache,simulation_identity


class FakeEngine:
    def __init__(self):
        pool,markets,rates=test_nba_pregame.PregameTests().fixture()
        original=PregameEngine(pool,markets,rates)
        self.__dict__.update(original.__dict__);self.calls=[]
    def __call__(self,n,seed):
        self.calls.append((n,seed));self.last_report=[{'seed':seed}]
        return np.random.default_rng(seed).random((n,len(self.pool))).astype(np.float32)


class SimulationCacheTests(unittest.TestCase):
    def setUp(self):clear_simulation_cache()
    def test_three_distinct_seeded_sets_reused_across_build_wrappers(self):
        first=FakeEngine();a=CachedNBAOutcomes(first)
        draws=[a(20,seed).copy() for seed in (83,1092,2100)]
        second=FakeEngine();b=CachedNBAOutcomes(second)
        for seed,expected in zip((83,1092,2100),draws):
            actual=b(20,seed)
            np.testing.assert_array_equal(actual,expected)
            self.assertTrue(b.last_cache_hit)
            self.assertFalse(actual.flags.writeable)
            b.last_report[0]['seed']=-1
        self.assertEqual(len(first.calls),3);self.assertEqual(second.calls,[])
        self.assertFalse(np.array_equal(draws[0],draws[1]))
        b(20,2100);self.assertEqual(b.last_report[0]['seed'],2100)

    def test_price_ownership_and_eligibility_do_not_change_physical_outcomes(self):
        a=FakeEngine();key=simulation_identity(a)
        a.pool['Salary']=6000;a.pool['Eligible']=False;a.pool['RotoWire Projected Own %']=99
        self.assertEqual(simulation_identity(a),key)

    def test_physical_input_changes_invalidate_including_one_float_step(self):
        base=FakeEngine();base.pool['Projection']=base.pool['Projection'].astype(float);key=simulation_identity(base)
        for column,value in [('Projection',np.nextafter(30.,31.)),('Projected Minutes',47.),('Injury Status','Out'),('Historical Shot Rate',2.)]:
            changed=deepcopy(base)
            changed.pool.at[0,column]=value
            self.assertNotEqual(simulation_identity(changed),key)
        changed=deepcopy(base);changed.rates=replace(base.rates,make_two=.54)
        self.assertNotEqual(simulation_identity(changed),key)
        changed=deepcopy(base);changed.platform='DraftKings'
        self.assertNotEqual(simulation_identity(changed),key)
        changed=deepcopy(base);changed.games[0][0]['implied_points']=(101,109)
        self.assertNotEqual(simulation_identity(changed),key)

    def test_count_is_part_of_cache_key(self):
        engine=FakeEngine();wrapped=CachedNBAOutcomes(engine)
        wrapped(20,83);wrapped(21,83)
        self.assertEqual(engine.calls,[(20,83),(21,83)])


if __name__=='__main__':unittest.main()
