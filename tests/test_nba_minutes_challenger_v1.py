import importlib.util
from pathlib import Path
import unittest
import pandas as pd
spec=importlib.util.spec_from_file_location('challenger',Path(__file__).parents[1]/'scripts'/'nba_minutes_challenger_v1.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PregameBoundaryTests(unittest.TestCase):
    def test_target_labels_cannot_change_current_features(self):
        rows=[dict(day=f'2026-11-{n:02}',game=str(n),team='A',pid='P',actual_minutes=20+n,actual_fp=30.,starter=True,dnp=False) for n in range(1,8)]
        a=pd.DataFrame(rows);before,_=m.features(a)
        a.loc[3,['actual_minutes','actual_fp','starter','dnp']]=[0,0,False,True]
        after,_=m.features(a)
        cols=['baseline',*m.FEATURES,'newest_history']
        pd.testing.assert_frame_equal(before[before.day=='2026-11-04'][cols].reset_index(drop=True),after[after.day=='2026-11-04'][cols].reset_index(drop=True))
        self.assertTrue((before.newest_history<before.day).all())

    def test_same_day_games_do_not_update_each_other(self):
        rows=[dict(day=f'2026-11-{n:02}',game=str(n),team='A',pid='P',actual_minutes=20.,actual_fp=30.,starter=False,dnp=False) for n in range(1,4)]
        rows.extend([dict(rows[-1],day='2026-11-04',game='4',actual_minutes=40.),dict(rows[-1],day='2026-11-04',game='5',actual_minutes=0.)])
        frame,_=m.features(pd.DataFrame(rows));self.assertEqual(frame.baseline.tolist(),[20.,20.])

if __name__=='__main__':unittest.main()
