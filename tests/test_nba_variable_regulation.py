import unittest
import numpy as np
from simmah_nba_minutes import draw_regulation_minutes
from simmah_nba_rotation_schedule import build_rotation
from simmah_nba_simulation_cache import simulation_identity
from simmah_nba_pregame import PregameEngine
import test_nba_pregame


class VariableRegulationTests(unittest.TestCase):
    def test_legal_rotations_and_preserved_role_means(self):
        means=np.array([48,38,36,33,26,24,18,10,6,1,0],float)
        samples=draw_regulation_minutes(means,10000,934)
        np.testing.assert_allclose(samples.sum(axis=1),240)
        np.testing.assert_allclose(samples.mean(axis=0),means,atol=.15)
        self.assertTrue((samples[:,0]==48).all() and (samples[:,-1]==0).all())
        self.assertGreater(np.std(samples[:,7]),2)
        np.testing.assert_array_equal(samples,draw_regulation_minutes(means,10000,934))
        self.assertFalse(np.array_equal(samples,draw_regulation_minutes(means,10000,935)))
        schedule=build_rotation(samples[:100],23)
        self.assertTrue((np.diff(np.sort(schedule,axis=-1),axis=-1)>0).all())
        for row,court in zip(samples,schedule):
            self.assertLess(np.max(abs(row-np.bincount(court.ravel(),minlength=len(row)))),1.00001)

    def test_mode_has_distinct_cache_identity(self):
        pool,markets,rates=test_nba_pregame.PregameTests().fixture()
        before=simulation_identity(PregameEngine(pool,markets,rates))
        pool.attrs['nba_variable_minutes']=True
        self.assertNotEqual(before,simulation_identity(PregameEngine(pool,markets,rates)))

    def test_wider_draw_preserves_mean_and_budget(self):
        from simmah_nba_minutes import draw_wider_minutes
        means=np.array([48,38,36,33,26,24,18,10,6,1,0],float)
        v=draw_wider_minutes(means,20000,83)
        np.testing.assert_allclose(v.sum(axis=1),240)
        np.testing.assert_allclose(v.mean(axis=0),means,atol=.2)
        self.assertTrue(((v>=0)&(v<=48)).all())
        self.assertTrue((v[:,0]==48).all() and (v[:,-1]==0).all())
        self.assertGreater(np.quantile(v[:,7],.99),np.quantile(draw_regulation_minutes(means,20000,83)[:,7],.99))
