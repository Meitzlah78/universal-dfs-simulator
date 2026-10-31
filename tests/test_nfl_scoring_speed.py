"""Speed paths must preserve the existing float scores, ranks, and payouts."""
import unittest
import numpy as np
import pandas as pd
from simmah_lineup_scores import LineupScorer
from simmah_contest_scoring import score_insertion_bounds
from simmah_contests import evaluate_contest, score_batch
from simmah_candidates import summarize_candidates


class ScoringSpeedTest(unittest.TestCase):
    def test_ordered_sparse_scores_match_slot_addition_exactly(self):
        rng=np.random.default_rng(87)
        for dtype in (np.float32,np.float64):
            for mult in (np.ones(6),np.array([1.5,1,1,1,1,1])):
                for output in (np.float32,np.float64):
                    values=rng.normal(size=(31,40)).astype(dtype)
                    picks=rng.integers(0,40,(300,6))  # Includes repeated IDs and unsorted slots.
                    weights=mult.astype(output)
                    expected=np.zeros((len(values),len(picks)),output)
                    for slot,weight in enumerate(weights):expected+=values[:,picks[:,slot]]*weight
                    before=values.copy()
                    actual=LineupScorer(picks,weights,40,dtype=output)(values)
                    np.testing.assert_array_equal(actual,expected)
                    np.testing.assert_array_equal(values,before)

    def test_adversarial_cancellation_and_strided_inputs(self):
        for dtype in (np.float32,np.float64):
            values=np.array([[2**24,1,-2**24,.1,.3,.7,9]],dtype=dtype)
            values=np.repeat(values,6,axis=0)[::2]
            picks=np.array([[0,1,2,3,4,5],[2,1,0,3,4,5],[0,0,1,2,4,3]])
            mult=np.array([1.5,1,1,1,1,1])
            np.testing.assert_array_equal(LineupScorer(picks,mult,7)(values),score_batch(values,picks,mult))

    def test_large_rank_queries_preserve_duplicates_boundaries_and_order(self):
        rng=np.random.default_rng(88)
        field=np.sort(rng.integers(-50,50,(9,1000)).astype(float),axis=1)
        queries=rng.integers(-80,80,(9,500)).astype(float)
        queries[:,::7]=0
        left,right=score_insertion_bounds(field,queries)
        for row in range(len(field)):
            np.testing.assert_array_equal(left[row],np.searchsorted(field[row],queries[row],'left'))
            np.testing.assert_array_equal(right[row],np.searchsorted(field[row],queries[row],'right'))

    def test_joint_candidate_summary_matches_original_numpy_path(self):
        rng=np.random.default_rng(89)
        outcomes=pd.DataFrame(rng.normal(size=(1000,40)).astype(np.float32),columns=[str(i) for i in range(40)])
        slots=['C','F1','F2','F3','F4','F5']
        frame=pd.DataFrame(rng.integers(0,40,(300,6)).astype(str),columns=slots)
        for mult in (None,[1.5,1,1,1,1,1]):
            actual=summarize_candidates(frame,outcomes,slots,mult)
            means=[];p95=[];p99=[]
            weights=np.ones(6) if mult is None else np.array(mult,np.float32)
            for start in range(0,len(frame),128):
                picks=frame.iloc[start:start+128].to_numpy(int)
                scores=np.zeros((len(outcomes),len(picks)),np.float32)
                for slot in range(6):scores+=outcomes.to_numpy()[:,picks[:,slot]]*weights[slot]
                means.extend(scores.mean(axis=0));p95.extend(np.quantile(scores,.95,axis=0));p99.extend(np.quantile(scores,.99,axis=0))
            np.testing.assert_array_equal(actual.SimMean,means)
            np.testing.assert_array_equal(actual.SimP95,p95)
            np.testing.assert_array_equal(actual.SimP99,p99)

    def test_weighted_contest_metrics_match_reference_kernels_exactly(self):
        from unittest.mock import patch
        rng=np.random.default_rng(90)
        outcomes=pd.DataFrame(rng.integers(-30,100,(37,45)).astype(np.float32)/10,
                              columns=[str(i) for i in range(45)])
        for width,mult in [(9,None),(6,[1.5,1,1,1,1,1])]:
            slots=[str(i) for i in range(width)]
            candidates=pd.DataFrame([rng.choice(outcomes.columns,width,replace=False) for _ in range(300)],columns=slots)
            field=pd.DataFrame([rng.choice(outcomes.columns,width,replace=False) for _ in range(700)],columns=slots)
            field.iloc[:10]=candidates.iloc[0].to_numpy()  # Exact ties and duplicate field copies.
            for joint in [False,True]:
                kwargs=dict(multipliers=mult,joint=joint)
                actual=evaluate_contest(outcomes,candidates,field,slots,1200,[(1,1,100),(2,10,10),(11,200,1)],.1,**kwargs)
                def original_scorer(picks,weights,players):
                    return lambda values: score_batch(values,picks,weights)
                def original_bounds(values,scores):
                    return (np.array([np.searchsorted(row,q,'left') for row,q in zip(values,scores)]),
                            np.array([np.searchsorted(row,q,'right') for row,q in zip(values,scores)]))
                with patch('simmah_lineup_scores.LineupScorer',side_effect=original_scorer), patch('simmah_contest_scoring.score_insertion_bounds',side_effect=original_bounds):
                    expected=evaluate_contest(outcomes,candidates,field,slots,1200,[(1,1,100),(2,10,10),(11,200,1)],.1,**kwargs)
                pd.testing.assert_frame_equal(actual,expected,check_exact=True)

    def test_invalid_indices_and_weights_rejected(self):
        for picks,weights in [(np.array([[0,-1]]),[1,1]),(np.array([[0,4]]),[1,1]),(np.array([[0,1]]),[1]),(np.array([[0,1]]),[1,float('nan')])]:
            with self.assertRaises(ValueError):LineupScorer(picks,weights,4)
