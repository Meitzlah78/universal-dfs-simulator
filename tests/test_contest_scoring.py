import ast
from pathlib import Path
import unittest
import numpy as np
from simmah_contest_scoring import score_insertion_bounds


class ContestScoringTest(unittest.TestCase):
    def test_bounds_include_duplicate_scores_and_extremes(self):
        field=np.array([[1,2,2,4],[0,0,0,0]],np.float32)
        candidates=np.array([[0,2,3,5],[-1,0,1,0]],np.float32)
        left,right=score_insertion_bounds(field,candidates)
        np.testing.assert_array_equal(left,[[0,1,3,4],[0,0,4,0]])
        np.testing.assert_array_equal(right,[[0,3,3,4],[0,4,4,4]])

    def test_random_bounds_match_scalar_reference(self):
        rng=np.random.default_rng(8)
        for dtype in [np.float32,np.float64]:
            field=np.sort(rng.integers(-20,20,(17,100)).astype(dtype),axis=1)
            candidates=rng.integers(-30,30,(17,50)).astype(dtype)
            left,right=score_insertion_bounds(field,candidates)
            np.testing.assert_array_equal(left,(field[:,:,None]<candidates[:,None,:]).sum(axis=1))
            np.testing.assert_array_equal(right,(field[:,:,None]<=candidates[:,None,:]).sum(axis=1))

    def test_shape_validation_and_empty_fields(self):
        for a,b in [(np.zeros(3),np.zeros((1,3))),(np.zeros((2,3)),np.zeros((1,3)))]:
            with self.assertRaises(ValueError):score_insertion_bounds(a,b)
        left,right=score_insertion_bounds(np.empty((2,0)),np.ones((2,3)))
        self.assertFalse(left.any());self.assertFalse(right.any())

    def test_app_metrics_match_reference_search_with_ties(self):
        from unittest.mock import patch
        tree=ast.parse(Path('dfs_app.py').read_text())
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='score_batch')
        def reference(field,candidates):
            left=np.empty(candidates.shape,dtype=np.int64)
            right=np.empty_like(left)
            for row in range(len(field)):
                for col,value in enumerate(candidates[row]):
                    left[row,col]=np.count_nonzero(field[row]<value)
                    right[row,col]=np.count_nonzero(field[row]<=value)
            return left,right
        rng=np.random.default_rng(9)
        for multiplier in [1.,1.5]:
            for candidates in [1,20]:
                for payouts in [None,np.r_[150.,100.,np.full(98,.2)]]:
                    ns=dict(np=np,simulation_values=rng.integers(0,8,(17,35)).astype(np.float32),
                        candidate_idx=rng.integers(0,35,(candidates,6)),contest_idx=rng.integers(0,35,(100,6)),
                        scoring_multiplier=multiplier,n_candidates=candidates,total_field=100,
                        estimated_full_field_size=35671,payout_schedule=payouts)
                    exec(compile(ast.Module(body=[fn],type_ignores=[]),'app-scoring','exec'),ns)
                    actual=ns['score_batch'](0,17)
                    with patch('simmah_contest_scoring.score_insertion_bounds',side_effect=reference):
                        expected=ns['score_batch'](0,17)
                    for a,b in zip(actual,expected):np.testing.assert_array_equal(a,b)
