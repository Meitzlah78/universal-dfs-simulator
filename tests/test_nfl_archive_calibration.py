import importlib.util
from pathlib import Path
import tempfile
import unittest
import pandas as pd
import numpy as np

spec=importlib.util.spec_from_file_location('archive_calibration',Path(__file__).resolve().parents[1]/'scripts'/'calibrate_nfl_archive.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ArchiveCalibrationTests(unittest.TestCase):
    def fixture(self,week):
        return pd.DataFrame({'season':[2026]*8,'week':[week]*8,'game_id':['game'+str(week)]*8,
            'play_id':range(8),'game_date':['2026-10-'+('12' if week==5 else '18')]*8,
            'qtr':[1,1,2,2,3,4,4,4],'game_seconds_remaining':[3000,2900,2000,1900,900,100,50,0],
            'play_type':['pass','pass','pass','pass','run','run','pass','run'],
            'down':[1,2,1,2,1,2,3,3],'sack':[1,0,0,0,0,0,0,0],
            'interception':[0,1,0,0,0,0,0,0],'complete_pass':[0,0,1,0,0,0,1,0],
            'yards_gained':[-6,0,12,0,4,5,9,3],'two_point_attempt':[0]*8})
    def test_fit_does_not_use_evaluation_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            train=Path(folder)/'train.csv';test=Path(folder)/'test.csv'
            self.fixture(5).to_csv(train,index=False);frame=self.fixture(6);frame.to_csv(test,index=False)
            before=module.calibrate(train,test)
            frame.loc[2,'complete_pass']=0
            frame.to_csv(test,index=False);after=module.calibrate(train,test)
            self.assertEqual([r['fitted'] for r in before['metrics']],[r['fitted'] for r in after['metrics']])
            self.assertNotEqual(before['metrics'][-1]['test_observed'],after['metrics'][-1]['test_observed'])
    def test_unknown_event_flags_rejected(self):
        frame=self.fixture(6);frame.loc[2,'complete_pass']=np.nan
        with self.assertRaises(ValueError):module.samples(frame)
    def test_overtime_and_conversions_excluded(self):
        frame=self.fixture(6);events,_=module.samples(frame)
        extra=frame.copy();extra['qtr']=5
        convert=frame.copy();convert['two_point_attempt']=1
        changed,_=module.samples(pd.concat([frame,extra,convert],ignore_index=True))
        for key in events:np.testing.assert_array_equal(events[key],changed[key])
    def test_duplicate_plays_and_wrong_week_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'data.csv';frame=self.fixture(5)
            frame.to_csv(path,index=False)
            with self.assertRaises(ValueError):module.load_archive(path,6)
            pd.concat([frame,frame.iloc[:1]]).to_csv(path,index=False)
            with self.assertRaises(ValueError):module.load_archive(path,5)
    def test_missing_end_marker_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'data.csv';frame=self.fixture(5);frame['game_seconds_remaining']=100
            frame.to_csv(path,index=False)
            with self.assertRaises(ValueError):module.load_archive(path,5)
