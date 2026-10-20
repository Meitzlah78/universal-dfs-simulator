import unittest
import numpy as np
from simmah_nba_roles import fit_roles, evaluate_roles

def game(day='2026-04-01', eid='1'):
    def row(pid, count):
        return {'athlete':{'id':pid},'stats':['20',f'2-{count}','2','4','1','0']}
    return {'event_id':eid,'date':day,'boxscore':{'players':[{'statistics':[
        {'names':['MIN','FG','AST','REB','STL','BLK'],
         'athletes':[row('a',10),row('b',2)]}]}]}}

class RoleTests(unittest.TestCase):
    def test_shrinkage_and_unseen_player_fallback(self):
        model=fit_roles([game()],'2026-04-02',20)
        self.assertAlmostEqual(model['players']['a']['rates'][0],.4)
        g=game('2026-04-02','2')
        g['boxscore']['players'][0]['statistics'][0]['athletes'][0]['athlete']['id']='new'
        report=evaluate_roles(model,[g],'2026-04-03')
        self.assertEqual(report['known_player_observations'],1)
        self.assertTrue(np.isfinite(list(report['player_rate_mae'].values())).all())

    def test_leakage_and_duplicate_guards(self):
        with self.assertRaises(ValueError):fit_roles([game()],'2026-04-01')
        with self.assertRaises(ValueError):fit_roles([game(),game()],'2026-04-02')
        model=fit_roles([game()],'2026-04-02')
        with self.assertRaises(ValueError):evaluate_roles(model,[game()],'2026-04-03')
