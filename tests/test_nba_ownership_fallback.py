import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import simmah_nba_pipeline as pipeline

class FallbackTests(unittest.TestCase):
    def run_case(self,absent=False):
        pool=pd.DataFrame({'Player ID':list(map(str,range(10)))})
        pool.attrs['platform']='DraftKings'
        ids=np.array([list(range(8)),list(range(7))+[8],list(range(7))+[9]])
        target=np.array([90]*7+[85,80,5],float)
        calls=[]
        real_sample=pipeline.sample_popularity_field
        def sample(lineups,weights,*args,**kwargs):
            calls.append(np.asarray(weights).copy())
            return real_sample(lineups,weights,*args,**kwargs)
        def factory(n,seed):return np.random.default_rng(seed).random((n,10))
        failure=ValueError('Ownership targets include players absent from legal field support') if absent else None
        with patch.object(pipeline,'build_candidates',return_value={'indices':ids,'unique':3}), \
             patch.object(pipeline,'build_field',side_effect=failure,return_value={'max_expected_error_pct':20}), \
             patch.object(pipeline,'ownership_support_diagnostic',return_value={'status':'inconclusive'}), \
             patch.object(pipeline,'sample_popularity_field',side_effect=sample), \
             patch.object(pipeline,'evaluate_candidates',return_value=pd.DataFrame()), \
             patch.object(pipeline,'select_entries',return_value=pd.DataFrame()):
            r=pipeline.run_pipeline(pool,factory,target,'verified test source',[1]+[0]*100,.25,1,simulations=3)
        np.testing.assert_array_equal(calls[0],target)
        f=r['field'];self.assertEqual(f['copies'].sum(),100)
        self.assertIn('relative popularity',f['fallback_mode'])
        self.assertIn('ownership_fit_warning',f)
        np.testing.assert_array_equal(f['ownership_target'],target)
        self.assertLess(f['ownership_expected'][9],f['ownership_expected'][8])
    def test_failed_residual_preserves_source_weights(self):self.run_case()
    def test_missing_support_preserves_source_weights(self):self.run_case(True)

if __name__=='__main__':unittest.main()
