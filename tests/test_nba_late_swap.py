import csv
import io
import unittest
import numpy as np
import pandas as pd
from simmah_nba_import import SLOTS
from simmah_nba_late_swap import swap_entries, export_swaps, locked_players, validate_swap, late_swap_filename


class LateSwapTests(unittest.TestCase):
    def test_started_zero_minutes_and_excluded_status_do_not_block_open_swaps(self):
        locked=locked_players(self.pool,self.now)
        self.pool['Eligible']=True;self.pool['Projected Minutes']=24.
        self.pool.loc[locked,'Eligible']=False
        self.pool.loc[locked,'Projected Minutes']=0.
        self.pool.loc[locked,'Injury Status']='Out'
        self.pool.loc[locked,'Projection']=0.
        original=np.arange(9)
        validate_swap(self.pool,original,original,locked)
        # An open player still has to meet current eligibility and projections.
        self.pool.loc[1,'Eligible']=False
        with self.assertRaises(ValueError):validate_swap(self.pool,original,original,locked)
    def setUp(self):
        self.pool=pd.DataFrame([{'Player ID':f'42-{i+1}','Name':f'Player {i}','Salary':5000,
            'Position':p,'Team':['A','B','C'][i%3],'Opponent':'D','Game':'A@D',
            'Injury Status':'Active','Projection':30+i,
            'Game Start':'2026-10-20T19:00:00-04:00' if i%3==0 else '2026-10-20T21:30:00-04:00'}
            for i,p in enumerate(['PG','SG','SF','PF','C','PG','PF','SG','C','SG','C','SF'])])
        self.ids=self.pool['Player ID'][:9].tolist()
        rows=[['entry_id','contest_id','contest_name','entry_fee',*SLOTS,'','keep'],
            ['123','42-99','NBA test','.05',*self.ids,'','preserve'],
            ['124','42-98','Other contest','.05',*self.ids],
            ['']*14+['Id','Nickname','Salary','Position','Team','Opponent','Game','Injury Indicator','Injury Details','FPPG']]
        for _,r in self.pool.iterrows():rows.append(['']*14+[r['Player ID'],r.Name,str(r.Salary),r.Position,r.Team,r.Opponent,r.Game,'','','30'])
        stream=io.StringIO();csv.writer(stream).writerows(rows);self.template=stream.getvalue().encode();self.rows=rows
        self.now=pd.Timestamp('2026-10-21T00:00:00Z')

    def test_site_slate_contest_and_eastern_time_identify_exports(self):
        self.pool.attrs['slate_date']='2026-10-20'
        name=late_swap_filename(self.pool,'42-99',now=self.now)
        self.assertEqual(name,'Simmah_FD_Late_Swap_2026-10-20_42-99_20261020_200000_EDT.csv')
        self.pool.attrs['platform']='DraftKings'
        name=late_swap_filename(self.pool,'197/99',automatic=True,now=self.now)
        self.assertEqual(name,'Simmah_DK_Auto_Late_Swap_2026-10-20_197-99_20261020_200000_EDT.csv')

    def test_locked_out_preserved_and_open_out_replaced_export_exact(self):
        self.pool.loc[0,'Injury Status']='Out';self.pool.loc[0,'Projection']=0
        self.pool.loc[1,'Injury Status']='Out'
        result=swap_entries(self.template,'42-99',self.pool,now=self.now)
        lineup=result['lineups'][0]
        for slot in [0,3,6]:self.assertEqual(lineup[slot],self.ids[slot])
        self.assertNotIn(self.ids[1],lineup)
        self.assertEqual(len(set(lineup)),9)
        rows=list(csv.reader(io.StringIO(export_swaps(self.template,'42-99',self.pool,result,now=self.now).decode())))
        self.assertEqual(rows[1][4:13],lineup)
        self.assertEqual(rows[1][:4],self.rows[1][:4]);self.assertEqual(rows[1][13:],self.rows[1][13:])
        self.assertEqual(rows[2:],self.rows[2:])
        with self.assertRaises(ValueError):export_swaps(self.template,'42-99',self.pool,result,now=self.now+pd.Timedelta(hours=3))

    def test_clock_missing_conflicting_and_exact_tip(self):
        self.assertEqual(locked_players(self.pool,pd.Timestamp('2026-10-20T23:00:00Z')).sum(),4)
        self.pool.loc[0,'Game Start']='2026-10-20T20:00:00-04:00'
        with self.assertRaises(ValueError):locked_players(self.pool,self.now)
        self.pool['Game Start']=None
        with self.assertRaises(ValueError):locked_players(self.pool,self.now)

    def test_timeout_and_all_locked_keep_entries(self):
        for now,seconds in [(self.now,0),(self.now+pd.Timedelta(hours=3),2)]:
            result=swap_entries(self.template,'42-99',self.pool,now=now,seconds=seconds)
            self.assertEqual(result['lineups'][0],self.ids)
            export_swaps(self.template,'42-99',self.pool,result,now=now)

    def test_new_started_players_and_cross_slate_rejected(self):
        locked=locked_players(self.pool,self.now)
        candidate=np.arange(9);candidate[1]=9
        with self.assertRaises(ValueError):validate_swap(self.pool,np.arange(9),candidate,locked)
        other=self.pool.copy();other.loc[0,'Player ID']='wrong'
        with self.assertRaises(ValueError):swap_entries(self.template,'42-99',other,now=self.now)

if __name__=='__main__':unittest.main()
