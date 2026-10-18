import unittest
import numpy as np
import pandas as pd
from simmah_projection_inputs import fit_projection_inputs
from simmah_nfl_engine import simulate_stat_lines
from test_nfl_engine import fixture,app_functions


class ProjectionInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool,cls.roles=fixture()
        cls.score=staticmethod(app_functions()['score_nfl_stat_line'])

    def test_quarterback_projection_changes_fresh_passing_production(self):
        pool=self.pool.copy()
        outputs=[]
        for target in [20.,8.]:
            pool.loc[pool.Name=='AQB','Projection']=target
            params,report=fit_projection_inputs(pool,self.roles,'FanDuel',self.score,pilot_n=768,iterations=5)
            raw=simulate_stat_lines(pool,self.roles,np.random.default_rng(991),3000,projection_inputs=params)
            outputs.append(float(np.mean(self.score(raw['AQB'],'FanDuel'))))
            self.assertTrue(np.isfinite(report['Pilot Mean']).all())
        self.assertLess(outputs[1],outputs[0]-4)

    def test_fitted_raw_stats_keep_passing_turnovers_and_scoreboard_links(self):
        params,report=fit_projection_inputs(self.pool,self.roles,'FanDuel',self.score,pilot_n=768,iterations=4)
        raw,games=simulate_stat_lines(self.pool,self.roles,np.random.default_rng(91),2000,projection_inputs=params,return_diagnostics=True)
        for team,other in [('A','B'),('B','A')]:
            for passing,receiving in [('passing_yards','receiving_yards'),('passing_tds','receiving_tds')]:
                np.testing.assert_allclose(raw[team+'QB'][passing],sum(raw[team+pos][receiving] for pos in ['RB','WR','TE']),atol=.001)
            np.testing.assert_array_equal(raw[team+'QB']['interceptions'],raw[other+'DST']['def_interceptions'])
            np.testing.assert_array_equal(raw[team+'DST']['points_allowed'],games[other]['chargeable'])
            g=games[team]
            np.testing.assert_array_equal(g['points'],6*(g['offensive_tds']+g['defensive_tds'])+2*g['safeties']+3*g['fg_made']+g['pat_made']+2*g['two_made'])
        self.assertTrue(report['Calibration Status'].str.contains('Unfitted').any())

    def test_calibration_does_not_consume_evaluation_rng_and_is_repeatable(self):
        a,ar=fit_projection_inputs(self.pool,self.roles,'FanDuel',self.score,pilot_n=256,iterations=2)
        b,br=fit_projection_inputs(self.pool,self.roles,'FanDuel',self.score,pilot_n=256,iterations=2)
        self.assertEqual(a,b);pd.testing.assert_frame_equal(ar,br)
        before=self.pool.copy(deep=True)
        simulate_stat_lines(self.pool,self.roles,np.random.default_rng(2),100,projection_inputs=a)
        pd.testing.assert_frame_equal(before,self.pool)

if __name__=='__main__':unittest.main()
