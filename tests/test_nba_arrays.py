import unittest
import numpy as np
from simmah_nba_arrays import score_batches

class NBAArrayTests(unittest.TestCase):
    def test_batched_scoring_matches_scalar_and_preserves_shared_scores(self):
        values=np.random.default_rng(12).integers(-3,70,(301,30)).astype(np.float32)
        indices=np.array([np.arange(9),np.arange(4,13),np.arange(9)])
        batches=list(score_batches(values,indices,64))
        self.assertEqual([s for s,_ in batches],[0,64,128,192,256])
        actual=np.concatenate([b for _,b in batches],axis=1)
        expected=np.array([[sum(values[j,i] for i in row) for j in range(len(values))] for row in indices])
        np.testing.assert_array_equal(actual,expected)
        np.testing.assert_array_equal(actual[0],actual[2])
    def test_invalid_indices_and_missing_scores_rejected(self):
        for outcomes,indices in [(np.ones((2,3)),np.array([[3]])),(np.array([[np.nan]]),np.array([[0]])),(np.ones((2,3)),np.array([[.5]]))]:
            with self.assertRaises(ValueError):list(score_batches(outcomes,indices))
