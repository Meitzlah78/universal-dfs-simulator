import unittest
from simmah_nba_possessions import reconstruct

def event(i,team,kind,clock='10:00',made=False,points=0):
    return {'id':str(i),'team':{'id':team},'type':{'text':kind},'period':{'number':1},
        'clock':{'displayValue':clock},'scoringPlay':made,'scoreValue':points,
        'shootingPlay':kind=='Jump Shot' or 'Free Throw' in kind}

class NBAPossessionTests(unittest.TestCase):
    def test_offensive_rebound_extends_and_defensive_rebound_ends(self):
        rows=[event(1,'A','Jump Shot'),event(2,'A','Offensive Rebound'),
            event(3,'A','Jump Shot'),event(4,'B','Defensive Rebound'),event(5,'B','Jump Shot','9:30',True,3)]
        p=reconstruct({'events':rows})
        self.assertEqual(len(p),2)
        self.assertEqual(p[0]['event_ids'],['1','2','3','4'])
        self.assertTrue(all(r['usable'] for r in p))
    def test_and_one_and_missed_final_free_throw(self):
        rows=[event(1,'A','Jump Shot',made=True,points=2),event(2,'B','Shooting Foul'),
            event(3,'A','Free Throw - 1 of 1',made=True,points=1),event(4,'B','Jump Shot','9:30'),
            event(5,'B','Free Throw - 1 of 2','9:29',True,1),event(6,'B','Free Throw - 2 of 2','9:29'),
            event(7,'B','Offensive Rebound','9:29'),event(8,'B','Shot Clock Turnover','9:25')]
        p=reconstruct({'events':rows})
        self.assertEqual(len(p),2);self.assertEqual(p[0]['points'],3)
        self.assertEqual(p[1]['end_reason'],'turnover')
    def test_unexplained_change_is_flagged(self):
        p=reconstruct({'events':[event(1,'A','Jump Shot'),event(2,'B','Jump Shot','9:50',True,2)]})
        self.assertFalse(p[0]['usable'])
        self.assertIn('unexplained_control_change',p[0]['flags'])
