import unittest
import numpy as np
from simmah_market_trial import implied_probability,parse_covers_pairs,tilt_outcomes
class MarketTrialTests(unittest.TestCase):
    def test_no_vig(self):
        p=implied_probability(-110);self.assertAlmostEqual(p/(p+p),.5)
        self.assertAlmostEqual(implied_probability(200),1/3)
    def doc(self,over='o10.5',under='u10.5'):
        return f'''<div><div class="playerContainer"><span class="category">Player</span></div><button class="compareOddsBtn" data-linkcont="x-nfl-receiving_yards-player"></button><dialog><table class="compareOddsTable"><tbody><tr><th><img alt="Book logo"></th><td><span class="oddsSideLineText">{over}</span><span class="americanOdds">-110</span></td><td><span class="oddsSideLineText">{under}</span><span class="americanOdds">-110</span></td></tr></tbody></table></dialog></div>'''
    def test_pairs_and_mismatch(self):
        rows,_=parse_covers_pairs(self.doc());self.assertEqual(len(rows),1);self.assertEqual(rows[0]['FairOver'],.5)
        self.assertEqual(parse_covers_pairs(self.doc(under='u11.5'))[0],[])
        self.assertEqual(parse_covers_pairs(self.doc(over='o10',under='u10'))[0],[])
    def test_joint_weight_fit_and_ess(self):
        x=np.arange(1000).reshape(-1,1)>500
        w,report=tilt_outcomes(x,[.7]);self.assertAlmostEqual(w.sum(),1)
        self.assertGreater(float(x[:,0]@w),.6)
        self.assertGreaterEqual(report['effective_sample_size'],250)
        np.testing.assert_allclose(w[:501],w[0])
    def test_invalid_probability(self):
        with self.assertRaises(ValueError):tilt_outcomes(np.ones((10,1)),[1.2])

class FrozenGradingTests(unittest.TestCase):
    def test_missing_game_cannot_be_zero(self):
        import pandas as pd
        from scripts.score_market_trial import grade
        with self.assertRaises(ValueError):grade(pd.DataFrame(),pd.DataFrame({'game_id':[]}))
    def test_raw_stat_scoring_and_unmatched(self):
        import pandas as pd
        from scripts.score_market_trial import grade
        trial=pd.DataFrame([dict(Platform=p,Name='QB',Position='QB',Baseline=20,Experimental=22) for p in ['DraftKings','FanDuel']])
        row=dict(game_id='2026_06_WAS_SF',player_display_name='QB',passing_yards=300,passing_tds=2,passing_interceptions=1,rushing_yards=20,rushing_tds=0,receiving_yards=0,receiving_tds=0,receptions=0,sack_fumbles_lost=1,rushing_fumbles_lost=0,receiving_fumbles_lost=0,passing_2pt_conversions=1,rushing_2pt_conversions=0,receiving_2pt_conversions=0)
        r=grade(trial,pd.DataFrame([row]));actual={x['Platform']:x['Actual'] for x in r['players']}
        self.assertEqual(actual,{'DraftKings':25.,'FanDuel':21.})

if __name__=='__main__':unittest.main()
