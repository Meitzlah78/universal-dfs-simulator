import unittest
from simmah_nba_rotation_triggers import Trigger,evaluate_triggers
from simmah_nba_rotation_validation import reconcile_boxscore

class RotationValidationTests(unittest.TestCase):
    def context(self,**kw):
        return dict(floor=['1','2','3','4','5'],active=[str(i) for i in range(1,10)],
            period=3,seconds_left=200,margin=16,fouls={'1':3},elapsed=2000,dead_ball=True,**kw)
    def test_priority_legality_cooldown_and_base(self):
        rules=[Trigger('margin',2,'2','7',min_margin=15,max_seconds_left=240),
               Trigger('fouls',1,'1','6',min_fouls=3,before_period=4)]
        out=evaluate_triggers(rules=rules,**self.context())
        self.assertEqual(out['floor'],('6','2','3','4','5'))
        ctx=self.context(last_fired={'fouls':1990})
        self.assertEqual(evaluate_triggers(rules=rules,**ctx)['reason'],'trigger: margin')
        ctx=self.context();ctx['dead_ball']=False
        self.assertEqual(evaluate_triggers(rules=rules,**ctx)['floor'],tuple(ctx['floor']))
        ctx=self.context();ctx['active'].remove('6')
        self.assertEqual(evaluate_triggers(rules=rules,**ctx)['reason'],'trigger: margin')
        ctx=self.context(base_due=True,base_floor=['1','2','3','4','9']);ctx['fouls']={};ctx['margin']=0
        self.assertEqual(evaluate_triggers(rules=rules,**ctx)['reason'],'base rotation')
    def fixture(self):
        teams=[{'teamId':str(t),'players':[{'personId':str(t*10+i),'played':'1','statistics':{'minutes':'PT48M00.00S'}} for i in range(5)]} for t in [1,2]]
        box={'game':{'gameId':'0042500101','gameStatus':3,'period':4,'homeTeam':teams[0],'awayTeam':teams[1]}}
        stints=[{'game_id':'42500101','team':str(t),'players':[str(t*10+i) for i in range(5)],'seconds':2880} for t in [1,2]]
        return stints,box
    def test_minutes_reconciled_and_unknown_not_zero(self):
        s,b=self.fixture();self.assertTrue(reconcile_boxscore(s,b)['passed'])
        b['game']['homeTeam']['players'][0]['personId']='999'
        r=reconcile_boxscore(s,b);self.assertFalse(r['passed'])
        self.assertTrue(any(p['actual_seconds'] is None for p in r['players']))
    def test_nonfinal_wrong_game_and_unknown_dnp_rejected(self):
        for mode in ['nonfinal','wronggame','missing']:
            s,b=self.fixture()
            if mode=='nonfinal':b['game']['gameStatus']=2
            elif mode=='wronggame':b['game']['gameId']='0042500102'
            else:b['game']['homeTeam']['players'][0]['statistics']['minutes']=None
            with self.assertRaises(ValueError):reconcile_boxscore(s,b)
