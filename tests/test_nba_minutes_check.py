import unittest
from copy import deepcopy
from test_nba_roles import game
from simmah_nba_minutes_check import check_minutes

def sample(day,eid,minutes=20,period=4):
    g=game(day,eid)
    g['events']=[{'period':{'number':period}}]
    for row in g['boxscore']['players'][0]['statistics'][0]['athletes']:
        row['stats'][0]=str(minutes)
    return g

class MinutesCheckTests(unittest.TestCase):
    def test_holdout_never_updates_training_and_ot_excluded(self):
        train=[sample('2026-04-01',str(i)) for i in range(3)]
        hold=[sample('2026-04-02','4',30),sample('2026-04-03','5',40),
              sample('2026-04-03','6',50,5)]
        r=check_minutes(train,hold,'2026-04-02','2026-04-04')
        self.assertEqual(r['covered_player_games'],4)
        self.assertEqual(r['last_three_mae'],15)
        self.assertEqual(r['last_three_bias'],-15)
        self.assertEqual(r['excluded_overtime_games'],1)

    def test_overlap_duplicate_and_sparse_history_rejected(self):
        g=sample('2026-04-01','1')
        with self.assertRaises(ValueError):
            check_minutes([g],[g],'2026-04-02','2026-04-04')
        with self.assertRaises(ValueError):
            check_minutes([g],[sample('2026-04-01','2')],'2026-04-02','2026-04-04')
        with self.assertRaises(ValueError):
            check_minutes([g],[sample('2026-04-03','2')],'2026-04-02','2026-04-04')
