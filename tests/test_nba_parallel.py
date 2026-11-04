import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import test_nba_pregame
from simmah_nba_pregame import PregameEngine
from simmah_nba_parallel import simulate_one_game,worker_count


class ParallelTests(unittest.TestCase):
    def fixture(self):
        p,m,r=test_nba_pregame.PregameTests().fixture()
        other=p.copy();other['Player ID']='x'+other['Player ID']
        other['Team']=other.Team.map({'A':'C','B':'D'});other['Opponent']=other.Opponent.map({'A':'C','B':'D'})
        return pd.concat([p,other],ignore_index=True),m+[{'teams':('C','D'),'implied_points':(105,115)}],r

    def test_worker_seed_offsets_and_prepared_parameters_match_serial(self):
        p,m,r=self.fixture();full=PregameEngine(p,m,r,parallel=False)
        expected=full(20,83);later=full(20,1092)
        for index in range(2):
            ids=np.arange(index*10,(index+1)*10);pool=p.iloc[ids].reset_index(drop=True)
            a,prepared,report=simulate_one_game((pool,m[index],r,4,'FanDuel',index,20,83,None))
            np.testing.assert_array_equal(a,expected[:,ids])
            b,_,_=simulate_one_game((pool,m[index],r,4,'FanDuel',index,20,1092,prepared))
            np.testing.assert_array_equal(b,later[:,ids])
            self.assertEqual(report['teams'],m[index]['teams'])

    def test_single_core_keeps_sequential_path(self):
        p,m,r=self.fixture();engine=PregameEngine(p,m,r)
        with patch('simmah_nba_parallel.worker_count',return_value=1),patch('simmah_nba_parallel.simulate_parallel') as parallel:
            engine(512,83)
            parallel.assert_not_called()

    def test_extra_workers_require_cpu_and_memory_headroom(self):
        def resource(path):
            return '400000 100000' if str(path).endswith('cpu.max') else '2147483648'
        cpu_api='os.process_cpu_count' if hasattr(__import__('os'),'process_cpu_count') else 'os.cpu_count'
        with patch('simmah_nba_parallel.'+cpu_api,return_value=8),patch('simmah_nba_parallel.os.sched_getaffinity',return_value=set(range(8))),patch('simmah_nba_parallel.Path.read_text',autospec=True,side_effect=resource):
            self.assertEqual(worker_count(),4)
        def small(path):
            return '400000 100000' if str(path).endswith('cpu.max') else '1073741824'
        with patch('simmah_nba_parallel.'+cpu_api,return_value=8),patch('simmah_nba_parallel.os.sched_getaffinity',return_value=set(range(8))),patch('simmah_nba_parallel.Path.read_text',autospec=True,side_effect=small):
            self.assertEqual(worker_count(),2)
        with patch('simmah_nba_parallel.'+cpu_api,return_value=8),patch('simmah_nba_parallel.os.sched_getaffinity',return_value={0}),patch('simmah_nba_parallel.Path.read_text',autospec=True,side_effect=resource):
            self.assertEqual(worker_count(),1)

    def test_workers_are_bounded_and_respect_quota(self):
        with patch('simmah_nba_parallel.Path.read_text',return_value='100000 100000'):
            self.assertEqual(worker_count(),1)
        self.assertLessEqual(worker_count(),4)


if __name__=='__main__':unittest.main()

