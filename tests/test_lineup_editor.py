import unittest
import pandas as pd
from simmah_lineup_editor import swap_player

class SwapTests(unittest.TestCase):
    def setUp(self):
        self.slots=['Captain','Flex1','Flex2','Flex3','Flex4','Flex5']
        self.pool=pd.DataFrame([{'Name':str(i),'Salary':5000,'Projection':10,'Position':'WR','Team':'A' if i%2 else 'B','Opponent':'B' if i%2 else 'A'} for i in range(8)])
        self.portfolio=pd.DataFrame([dict(zip(self.slots,map(str,range(6)))),dict(zip(self.slots,map(str,[1,0,2,3,4,5])))])
        self.portfolio['Top1']=.2
    def test_accepted_swap_updates_salary_and_removes_stale_metrics(self):
        r=swap_player(self.portfolio,self.pool,self.slots,0,'Captain','6','DraftKings')
        self.assertEqual(r.iloc[0]['Captain'],'6');self.assertEqual(r.iloc[0]['Salary'],32500)
        self.assertNotIn('Top1',r);self.assertEqual(self.portfolio.iloc[0]['Captain'],'0')
    def test_duplicates_and_missing_projection_rejected(self):
        with self.assertRaises(ValueError):swap_player(self.portfolio,self.pool,self.slots,0,'Captain','1','DraftKings')
        self.pool.loc[self.pool.Name=='6','Projection']=0
        with self.assertRaises(ValueError):swap_player(self.portfolio,self.pool,self.slots,0,'Captain','6','DraftKings')
    def test_salary_and_selected_rules_rejected(self):
        self.pool.loc[self.pool.Name=='6','Salary']=30000
        with self.assertRaises(ValueError):swap_player(self.portfolio,self.pool,self.slots,0,'Captain','6','DraftKings')
        with self.assertRaises(ValueError):swap_player(self.portfolio,self.pool,self.slots,0,'Captain','7','FanDuel',lambda row:False)
    def test_classic_position_and_defense(self):
        slots=['QB','RB1','DST'];pool=pd.DataFrame([
            dict(Name='Q',Salary=5000,Projection=10,Position='QB',Team='A',Opponent='B'),
            dict(Name='R',Salary=5000,Projection=10,Position='RB',Team='C',Opponent='D'),
            dict(Name='D',Salary=5000,Projection=10,Position='DST',Team='E',Opponent='F'),
            dict(Name='X',Salary=5000,Projection=10,Position='RB',Team='F',Opponent='E')])
        p=pd.DataFrame([dict(QB='Q',RB1='R',DST='D')])
        with self.assertRaises(ValueError):swap_player(p,pool,slots,0,'QB','X','DraftKings')
        with self.assertRaises(ValueError):swap_player(p,pool,slots,0,'RB1','X','DraftKings')
