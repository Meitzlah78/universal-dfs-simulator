import unittest
from simmah_nba_rotations import reconstruct_rotations, seconds

class NBARotationTests(unittest.TestCase):
    def test_decimal_clock(self):
        self.assertEqual(seconds({"clock":{"displayValue":"7.8"}}),7.8)

    def game(self):
        groups=[{'team':{'id':t},'statistics':[{'athletes':[{'athlete':{'id':t+str(i)},'starter':i<5} for i in range(6)]}]} for t in ['A','B']]
        def e(i,kind,clock,participants=()):
            return {'id':str(i),'period':{'number':1},'clock':{'displayValue':clock},'team':{'id':'A'},'type':{'text':kind},'participants':[{'athlete':{'id':p}} for p in participants]}
        return {'boxscore':{'players':groups},'events':[e(1,'Jump Shot','11:00',['A0']),e(2,'Substitution','6:00',['A5','A0']),e(3,'End Period','0:00')]}
    def test_five_players_and_team_minutes_conserved(self):
        result=reconstruct_rotations(self.game())
        self.assertTrue(result['complete'])
        self.assertTrue(all(len(s['players'])==5 for s in result['stints']))
        self.assertAlmostEqual(sum(result['player_minutes'].values()),120)
        self.assertEqual(result['player_minutes']['A0'],6)
        self.assertEqual(result['player_minutes']['A5'],6)
    def test_bad_substitution_is_not_silently_repaired(self):
        game=self.game();game['events'][1]['participants'][0]['athlete']['id']='A1'
        result=reconstruct_rotations(game)
        self.assertFalse(result['complete'])
        self.assertEqual(result['issues'][0]['reason'],'invalid_substitution')
