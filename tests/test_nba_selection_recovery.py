import hashlib,io,json,unittest,zipfile
from unittest.mock import patch
import numpy as np,pandas as pd
from simmah_nba_pipeline import run_pipeline,NBASelectionFailure
from simmah_nba_contest import select_entries,evaluate_candidates
from simmah_nba_candidates import build_candidates
from simmah_nba_diagnostics import make_selection_failure_package
import test_nba_candidates

ERROR='Portfolio repair reached its search limit without a valid full portfolio. Manual exposure limits were kept; no duplicates were added.'

class RecoveryTests(unittest.TestCase):
    def fixture(self):
        pool,_=test_nba_candidates.CandidateTests().fixture();pool['Name']=pool['Player ID'];pool['Opponent']='E';pool['Game']='A@E'
        calls=[]
        def factory(n,seed):calls.append(seed);return np.random.default_rng(seed).gamma(4,8,(n,len(pool)))
        def execute():
            return run_pipeline(pool,factory,np.full(len(pool),22.5),'synthetic balanced ownership',
                [1]*10+[0]*91,.05,5,simulations=20,candidate_target=100,field_support_target=100,
                diversity=0,excluded_indices=[0],capture_diagnostics=True)
        return pool,calls,execute

    def test_recovery_preserves_outcomes_field_exclusions_and_all_old_candidates(self):
        pool,calls,execute=self.fixture();selected_calls=[]
        def select(*args,**kwargs):
            selected_calls.append(args[1].copy())
            if len(selected_calls)==1:raise ValueError(ERROR)
            return select_entries(*args,**kwargs)
        with patch('simmah_nba_pipeline.select_entries',side_effect=select),patch('simmah_nba_pipeline.evaluate_candidates',wraps=evaluate_candidates) as scoring,patch('simmah_nba_pipeline.build_candidates',wraps=build_candidates) as build:
            result=execute()
        self.assertEqual(calls,[83,1092,2100])
        self.assertIsNotNone(result['candidate_recovery'])
        np.testing.assert_array_equal(selected_calls[0],selected_calls[1][:len(selected_calls[0])])
        self.assertFalse((selected_calls[1]==0).any())
        self.assertEqual(len(np.unique(np.sort(selected_calls[1],axis=1),axis=0)),len(selected_calls[1]))
        self.assertEqual(len(result['report']),len(result['candidates']['indices']))
        self.assertEqual(len(result['portfolio']),5)
        self.assertEqual(scoring.call_count,2)
        first,second=[c.args for c in scoring.call_args_list]
        np.testing.assert_array_equal(first[0],second[0]);np.testing.assert_array_equal(first[2],second[2])
        self.assertEqual(build.call_args_list[-1].kwargs['search_noise'],.6)
        self.assertEqual(build.call_args_list[-1].kwargs['seed'],3084)

    def test_repeat_failure_preserves_full_recovery_evidence(self):
        pool,calls,execute=self.fixture()
        with patch('simmah_nba_pipeline.select_entries',side_effect=ValueError(ERROR)):
            with self.assertRaises(NBASelectionFailure) as failure:execute()
        exc=failure.exception
        self.assertGreater(len(exc.candidates),100)
        self.assertEqual(len(exc.candidates),len(exc.report))
        self.assertEqual(exc.settings['portfolio_count'],5)
        name,raw,manifest=make_selection_failure_package(pool,exc.candidates,exc.report,{'id':'1'},exc.settings,str(exc))
        self.assertIn('Portfolio_Failure.zip',name)
        self.assertEqual(manifest['kind'],'nba_portfolio_selection_failure')
        archive=zipfile.ZipFile(io.BytesIO(raw))
        for path,entry in manifest['files'].items():self.assertEqual(hashlib.sha256(archive.read(path)).hexdigest(),entry['sha256'])
        self.assertEqual(len(pd.read_csv(archive.open('candidate_lineups.csv'))),len(exc.candidates))
        self.assertIn('inputs/hard_limits.json',archive.namelist())

    def test_other_selection_errors_do_not_launch_broader_search(self):
        pool,calls,execute=self.fixture()
        with patch('simmah_nba_pipeline.select_entries',side_effect=ValueError('Invalid manual controls')),patch('simmah_nba_pipeline.build_candidates',wraps=build_candidates) as build:
            with self.assertRaisesRegex(NBASelectionFailure,'Invalid manual controls'):execute()
        self.assertFalse(any('search_noise' in call.kwargs for call in build.call_args_list))

if __name__=='__main__':unittest.main()
