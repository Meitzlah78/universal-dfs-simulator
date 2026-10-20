import unittest
from simmah_nba_fit import fit_baseline

class NBAFitTests(unittest.TestCase):
    def game(self,day='2025-10-21',eid='1'):
        values={'fieldGoalsMade-fieldGoalsAttempted':'40-90','threePointFieldGoalsMade-threePointFieldGoalsAttempted':'10-30',
            'freeThrowsMade-freeThrowsAttempted':'20-25','assists':'25','steals':'7','blocks':'4','totalTurnovers':'15','offensiveRebounds':'10','defensiveRebounds':'30'}
        team={'statistics':[{'name':k,'displayValue':v} for k,v in values.items()]}
        return {'event_id':eid,'date':day,'events':[{'period':{'number':4}}],'boxscore':{'teams':[team,team]}}
    def test_pooled_event_rate_denominators(self):
        r=fit_baseline([self.game()],'2026-10-20',minimum_games=1)['rates']
        self.assertAlmostEqual(r.make_two,.5)
        self.assertAlmostEqual(r.three_share,1/3)
        self.assertAlmostEqual(r.assisted,.625)
        self.assertAlmostEqual(r.seconds_per_action,2880/235)
    def test_future_duplicate_and_small_samples_rejected(self):
        with self.assertRaises(ValueError):fit_baseline([self.game()],'2026-10-20')
        with self.assertRaises(ValueError):fit_baseline([self.game('2026-10-20')],'2026-10-20',1)
        with self.assertRaises(ValueError):fit_baseline([self.game(),self.game()],'2026-10-20',1)
