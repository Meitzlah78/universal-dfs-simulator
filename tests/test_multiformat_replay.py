import importlib.util
from pathlib import Path
import unittest
import tempfile
import json
import numpy as np
import pandas as pd

spec=importlib.util.spec_from_file_location('multi_replay',Path(__file__).resolve().parents[1]/'scripts'/'replay_portfolio_methods.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class MultiFormatReplayTests(unittest.TestCase):
    def test_eight_and_nine_slot_rosters_remain_intact_and_outcome_blind(self):
        for size in (8,9):
            slots=['S'+str(i) for i in range(size)]
            frame=pd.DataFrame([{**{slot:str((i+j)%24) for j,slot in enumerate(slots)},'_top1':24-i,'actual':i} for i in range(24)])
            controls={'0':{'Max Exposure %':50},'23':{'Fade':True}}
            first,info=m.portfolios(frame,slots,4,controls,50,trials=10,seed=3)
            frame.actual=frame.actual.iloc[::-1].to_numpy()*1000
            second,_=m.portfolios(frame,slots,4,controls,50,trials=10,seed=3)
            originals={tuple(row) for row in frame[slots].to_numpy()}
            self.assertEqual(info['accepted'],10)
            for method,item in first.items():
                self.assertNotIn('error',item,method)
                chosen=item['portfolio']
                pd.testing.assert_frame_equal(chosen[slots],second[method]['portfolio'][slots])
                self.assertTrue(all(tuple(row) in originals for row in chosen[slots].to_numpy()))
                self.assertFalse(chosen[slots].eq('23').any().any())
                self.assertLessEqual(chosen[slots].eq('0').any(axis=1).sum(),2)

    def test_role_caps_minima_locks_and_absent_locked_player(self):
        frame=pd.DataFrame({'Captain':['A','B','C','D'],'FLEX1':['B','A','A','A'],'_top1':[4,3,2,1]})
        controls={'A':{'Lock':True,'Captain Max %':50,'Flex Max %':50}}
        matrix,lo,hi=m.constraints(frame,['Captain','FLEX1'],2,controls)
        output,_=m.portfolios(frame,['Captain','FLEX1'],2,controls,0,trials=10,seed=8)
        for method,item in output.items():
            self.assertNotIn('error',item,method)
            table=item['portfolio']
            self.assertEqual(table[['Captain','FLEX1']].eq('A').any(axis=1).sum(),2)
            self.assertLessEqual(table.Captain.eq('A').sum(),1)
            self.assertLessEqual(table.FLEX1.eq('A').sum(),1)
        counts=matrix[[0,1]].sum(axis=0)
        self.assertTrue(((counts>=lo)&(counts<=hi)).all())
        counts=matrix[[1,2]].sum(axis=0)
        self.assertFalse(((counts>=lo)&(counts<=hi)).all())
        _,lo,_=m.constraints(frame,['Captain','FLEX1'],2,{'X':{'Lock':True}})
        self.assertGreater(lo.max(),0)

    def test_interchangeable_slot_duplicates_removed_special_identity_kept(self):
        frame=pd.DataFrame({'Captain':['A','A','B'],'FLEX1':['B','C','A'],'FLEX2':['C','B','C'],'_top1':[3,2,1]})
        self.assertEqual(len(m.prepare(frame,['Captain','FLEX1','FLEX2'])),2)
        self.assertEqual(len(m.prepare(frame,['FLEX1','FLEX2'])),2)

    def test_ledger_groups_contests_and_deduplicates_replays(self):
        report={key:None for key in ('format','contest_id','build_sha256','standings_sha256','protocol_version','methods','random_summary','random_sampling','swap_random_summary')}
        report.update(slate_group='NBA-2026-10-31-main',format='nba_dk',contest_id='1')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.json'
            m.update_ledger(path,report);m.update_ledger(path,report)
            report.update(format='nba_fd',contest_id='2');m.update_ledger(path,report)
            ledger=json.loads(path.read_text())
            self.assertEqual(len(ledger['groups']),1)
            self.assertEqual(len(ledger['groups'][report['slate_group']]),2)
            report['slate_group']='wrong-group'
            with self.assertRaises(ValueError):m.update_ledger(path,report)

    def test_random_failure_reports_unavailable_without_relaxation(self):
        frame=pd.DataFrame({'S1':['A','A','A'],'S2':['B','C','D'],'_top1':[3,2,1]})
        output,info=m.portfolios(frame,['S1','S2'],2,{'A':{'Max Exposure %':0}},0,trials=1)
        self.assertIn('error',output['random'])
        self.assertEqual(info['accepted'],0)
        self.assertIn('error',output['distance'])

if __name__=='__main__':unittest.main()
