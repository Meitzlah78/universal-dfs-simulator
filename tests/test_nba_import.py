import csv
import io
import unittest
from simmah_nba_import import read_template, SLOTS

class NBAImportTests(unittest.TestCase):
    def template(self):
        rows=[['entry_id','contest_id','contest_name','entry_fee',*SLOTS],
            ['123','42-99','NBA test','.05',*(['']*9)],
            ['Id','Nickname','Salary','Position','Team','Opponent','Game','Injury Indicator','Injury Details','FPPG'],
            ['42-10','Player One','9000','PG/SG','A','B','A@B','Q','','45']]
        f=io.StringIO();csv.writer(f).writerows(rows);return f.getvalue().encode()
    def test_ids_slots_and_historical_points_are_preserved(self):
        result=read_template(self.template());p=result['players'].iloc[0]
        self.assertEqual(result['slots'],SLOTS)
        self.assertEqual(result['entries'][0][0],'123')
        self.assertEqual(p['Historical FPPG'],45)
        self.assertIsNone(p['Projection'])
        self.assertEqual(p['Injury Status'],'Questionable')
    def test_wrong_sport_and_cross_slate_rejected(self):
        for data in (self.template().replace(b'PG,SG,SF',b'QB,RB,WR'),self.template().replace(b'42-99',b'77-99')):
            with self.assertRaises(ValueError):read_template(data)
