import unittest
import numpy as np
import pandas as pd
from simmah_nba_minutes_uncertainty import fit_team_residuals,sample_team_minutes
from simmah_nba_rotation_schedule import build_rotation

class TeamMinutesTests(unittest.TestCase):
    def records(self):
        rows=[]
        for game,delta in enumerate([-4,0,4]):
            for i in range(8):
                rows.append({'Game ID':str(game),'Team':'A','Player ID':str(i),
                    'GameStart':f'2026-01-0{game+1}T23:00Z','CapturedAt':f'2026-01-0{game+1}T22:00Z',
                    'Final':True,'Overtime':False,'Projected Minutes':30,
                    'Actual Minutes':30+(delta if i==0 else -delta if i==1 else 0)})
        return pd.DataFrame(rows)
    def test_joint_samples_legal_reproducible_and_rotation_compatible(self):
        model=fit_team_residuals(self.records(),'2026-02-01T00:00Z')
        result=sample_team_minutes(model,'A',list(map(str,range(8))),[30]*8,1000,83)
        np.testing.assert_allclose(result.sum(axis=1),240)
        self.assertTrue(((result>=0)&(result<=48)).all())
        self.assertLess(np.cov(result[:,0],result[:,1])[0,1],0)
        np.testing.assert_array_equal(result,sample_team_minutes(model,'A',list(map(str,range(8))),[30]*8,1000,83))
        rotation=build_rotation(result[:20],83)
        self.assertEqual(rotation.shape,(20,48,5))
    def test_leakage_overtime_and_incomplete_data_rejected(self):
        for column,value in [('CapturedAt','2026-03-01T00:00Z'),('Overtime',True),('Final',False),('Actual Minutes',0)]:
            rows=self.records();rows.loc[0,column]=value
            with self.assertRaises(ValueError):fit_team_residuals(rows,'2026-02-01T00:00Z')
        model=fit_team_residuals(self.records(),'2026-02-01T00:00Z')
        with self.assertRaises(ValueError):sample_team_minutes(model,'B',list(map(str,range(8))),[30]*8,10,83)
    def test_holdout_is_frozen_and_reports_uncovered_teams(self):
        from simmah_nba_minutes_uncertainty import evaluate_team_minutes
        training=self.records();model=fit_team_residuals(training,'2026-02-01T00:00Z')
        held=training[training['Game ID']=='0'].copy()
        held['GameStart']='2026-02-02T23:00Z';held['CapturedAt']='2026-02-02T22:00Z'
        result=evaluate_team_minutes(model,held)
        self.assertEqual(result['matched_player_games'],8)
        self.assertIsNotNone(result['coverage_80'])
        held['Team']='B'
        self.assertEqual(len(evaluate_team_minutes(model,held)['uncovered_team_games']),1)
        with self.assertRaises(ValueError):evaluate_team_minutes(model,training)
