import unittest,csv,io
import pandas as pd
from simmah_nba_rosters import validate_lineup,export_entries
from simmah_nba_import import SLOTS

class NBARosterTests(unittest.TestCase):
    def setUp(self):
        self.pool=pd.DataFrame([{'Player ID':f'42-{i+1}','Name':f'Player {i}','Salary':5000,
            'Position':p,'Team':['A','B','C'][i%3],'Opponent':'D','Game':'A@D',
            'Injury Status':'Active','Projection':30} for i,p in enumerate(['PG','SG','SF','PF','C','PG','PF','SG','C'])])
        self.ids=self.pool['Player ID'].tolist()
    def test_flexible_slots_and_hard_limits(self):
        self.assertEqual(validate_lineup(self.pool,self.ids,salary_cap=60000,max_from_team=4),45000)
        bad=self.ids.copy();bad[5],bad[8]=bad[8],bad[5]
        with self.assertRaises(ValueError):validate_lineup(self.pool,bad,salary_cap=60000,max_from_team=4)
        self.pool.loc[0,'Projection']=0
        with self.assertRaises(ValueError):validate_lineup(self.pool,self.ids,salary_cap=60000,max_from_team=4)
    def test_export_preserves_entry_and_reference_cells(self):
        rows=[['entry_id','contest_id','contest_name','entry_fee',*SLOTS,'','Instructions'],
            ['3749903854','42-99','NBA test','.05',*(['']*9),'','keep me'],
            ['','','','','','','','','','','','','','','Id','Nickname','Salary','Position','Team','Opponent','Game','Injury Indicator','Injury Details','FPPG']]
        for r in self.pool.itertuples(index=False):
            rows.append(['']*14+[getattr(r,'_0'),r.Name,str(r.Salary),r.Position,r.Team,r.Opponent,r.Game,'','','30'])
        f=io.StringIO();csv.writer(f).writerows(rows);data=f.getvalue().encode()
        result=list(csv.reader(io.StringIO(export_entries(data,[self.ids],'42-99',self.pool,salary_cap=60000,max_from_team=4).decode())))
        self.assertEqual(result[1][0],'3749903854');self.assertEqual(result[1][4:13],self.ids)
        self.assertEqual(result[1][14],'keep me');self.assertEqual(result[2:],rows[2:])
