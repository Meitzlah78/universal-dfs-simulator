import unittest
import numpy as np
from simmah_nba_minutes import draw_wider_minutes
from simmah_nba_shared_bench_offline import draw_bench_minutes

class SharedBenchTests(unittest.TestCase):
    def means(self):return np.array([38.,36.,34.,32.,30.,28.,16.,14.,12.,0.])
    def test_control_exactly_reproduces_production_and_is_deterministic(self):
        m=self.means()
        np.testing.assert_array_equal(draw_bench_minutes(m,1000,83,shared=False),draw_wider_minutes(m,1000,83))
        np.testing.assert_array_equal(draw_bench_minutes(m,1000,83),draw_bench_minutes(m,1000,83))
    def test_conservation_bounds_and_zero_reserve(self):
        x=draw_bench_minutes(self.means(),10000,83)
        np.testing.assert_allclose(x.sum(1),240,rtol=0,atol=1e-10)
        self.assertTrue((x>=0).all());self.assertTrue((x<=48).all());self.assertTrue((x[:,-1]==0).all())
    def test_mean_and_marginal_variance_preserved_while_joint_tail_changes(self):
        m=self.means();a=draw_bench_minutes(m,50000,84,shared=False);b=draw_bench_minutes(m,50000,84)
        np.testing.assert_allclose(a.mean(0),m,atol=.16);np.testing.assert_allclose(b.mean(0),m,atol=.16)
        np.testing.assert_allclose(a.var(0),b.var(0),rtol=.07,atol=.3)
        self.assertGreater(((b[:,6]>m[6]+5)&(b[:,7]>m[7]+5)).mean(),((a[:,6]>m[6]+5)&(a[:,7]>m[7]+5)).mean())
    def test_invalid_rotation_rejected(self):
        for m in [np.ones(8)*20,np.array([48.]*4),np.array([np.nan]*10)]:
            with self.assertRaises(ValueError):draw_bench_minutes(m,10,83)
