import unittest
from unittest.mock import patch
from copy import deepcopy
import numpy as np
from scripts.nba_conditional_check import check
from simmah_nba_engine import EventRates

class ConditionalCheckTests(unittest.TestCase):
    def game(self,day,eid,points=20):
        teams=[]
        for t in range(2):
            athletes=[{'athlete':{'id':str(t*5+i)},'stats':['48',str(points)]} for i in range(5)]
            teams.append({'statistics':[{'names':['MIN','PTS'],'athletes':athletes}]})
        return {'date':day,'event_id':eid,'events':[{'period':{'number':4}}],
                'boxscore':{'players':teams}}
    def test_actual_points_are_only_evaluation_targets(self):
        train=[self.game('2026-04-01','1')];hold=self.game('2026-04-02','2')
        rates=EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)
        model={'players':{},'pooled_rates':[1]*5}
        with patch('scripts.nba_conditional_check.fit_baseline',return_value={'rates':rates}), \
             patch('scripts.nba_conditional_check.fit_roles',return_value=model):
            a=check(train,[hold],'2026-04-02','2026-04-03',10)
            for team in hold['boxscore']['players']:
                for row in team['statistics'][0]['athletes']:row['stats'][1]='30'
            b=check(train,[hold],'2026-04-02','2026-04-03',10)
        self.assertEqual(a['games'][0]['sim_mean_team_points'],b['games'][0]['sim_mean_team_points'])
        self.assertNotEqual(a['games'][0]['actual_team_points'],b['games'][0]['actual_team_points'])
    def test_duplicate_training_holdout_rejected(self):
        g=self.game('2026-04-01','1')
        with self.assertRaises(ValueError):check([g],[g],'2026-04-02','2026-04-03')
        with self.assertRaises(ValueError):check([],[],'2026-04-02','2026-04-03',0)
