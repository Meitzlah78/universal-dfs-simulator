import unittest

import numpy as np

from dk_showdown_engine import weighted_score_bounds


def tied_prize(left, right, payout_by_rank):
    """Prize for one candidate added to an opponent field with [left,right) ties."""
    payout = np.asarray(payout_by_rank, dtype=np.float64)
    prefix = np.concatenate(([0.0], np.cumsum(payout)))
    start = np.asarray(left, dtype=np.int64)
    stop = np.asarray(right, dtype=np.int64) + 1  # include candidate itself
    safe_start = np.clip(start, 0, len(payout))
    safe_stop = np.clip(stop, 0, len(payout))
    prize_sum = prefix[safe_stop] - prefix[safe_start]
    tie_size = stop - start
    return np.divide(prize_sum, tie_size, out=np.zeros_like(prize_sum), where=tie_size > 0)


class DKShowdownROIInvariantTests(unittest.TestCase):
    def test_exact_duplicate_candidate_splits_all_occupied_prizes(self):
        # Three opponent copies score 110. Candidate is the fourth exact-score
        # entry. One opponent at 120 is ahead, so the four-way tie occupies
        # ranks 2-5 and must share those four prizes equally.
        unique_scores = np.array([[120.0, 110.0, 95.0]], dtype=np.float32)
        counts = np.array([1, 3, 5], dtype=np.int64)
        candidate = np.array([[110.0]], dtype=np.float32)
        left, right = weighted_score_bounds(unique_scores, counts, candidate)
        payout = np.array([250.0, 150.0, 100.0, 75.0, 50.0, 40.0, 30.0, 30.0, 25.0, 25.0])
        actual = tied_prize(left, right, payout)[0, 0]
        self.assertEqual(actual, (150.0 + 100.0 + 75.0 + 50.0) / 4.0)

    def test_duplicate_tie_crossing_cash_line_shares_unpaid_ranks(self):
        # Five copies tie the candidate at 90. Four entries are ahead. The
        # six-way tie occupies ranks 5-10 while only ranks 5-7 pay. Unpaid tied
        # ranks still share the available prize pool.
        unique_scores = np.array([[120.0, 110.0, 100.0, 95.0, 90.0]], dtype=np.float32)
        counts = np.array([1, 1, 1, 1, 5], dtype=np.int64)
        candidate = np.array([[90.0]], dtype=np.float32)
        left, right = weighted_score_bounds(unique_scores, counts, candidate)
        payout = np.array([100.0, 60.0, 40.0, 20.0, 10.0, 8.0, 6.0])
        actual = tied_prize(left, right, payout)[0, 0]
        self.assertEqual(actual, (10.0 + 8.0 + 6.0) / 6.0)

    def test_entry_fee_roi_identity(self):
        prizes = np.array([0.0, 0.05, 0.10, 0.25, 1.00], dtype=np.float64)
        entry_fee = 0.10
        expected_prize = float(prizes.mean())
        expected_net = expected_prize - entry_fee
        expected_roi_pct = 100.0 * expected_net / entry_fee
        self.assertAlmostEqual(expected_prize, 0.28)
        self.assertAlmostEqual(expected_net, 0.18)
        self.assertAlmostEqual(expected_roi_pct, 180.0)


if __name__ == "__main__":
    unittest.main()
