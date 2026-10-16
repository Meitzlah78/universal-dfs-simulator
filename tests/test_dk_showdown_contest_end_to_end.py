import unittest

import numpy as np

from dk_showdown_engine import duplicate_expansion_counts, weighted_score_bounds


def tied_prize(left, right, payout_by_rank):
    payout = np.asarray(payout_by_rank, dtype=np.float64)
    prefix = np.concatenate(([0.0], np.cumsum(payout)))
    start = np.asarray(left, dtype=np.int64)
    stop = np.asarray(right, dtype=np.int64) + 1
    safe_start = np.clip(start, 0, len(payout))
    safe_stop = np.clip(stop, 0, len(payout))
    prize_sum = prefix[safe_stop] - prefix[safe_start]
    tie_size = stop - start
    return np.divide(prize_sum, tie_size, out=np.zeros_like(prize_sum), where=tie_size > 0)


class DKShowdownContestEndToEndTests(unittest.TestCase):
    def test_compressed_duplicate_field_matches_expanded_contest_prizes(self):
        rng = np.random.default_rng(20261020)
        unique_count = 2_500
        full_field_size = 10_000
        sims = 250
        candidates = 12

        log_popularity = rng.normal(-14.0, 2.0, size=unique_count)
        counts = duplicate_expansion_counts(log_popularity, full_field_size, seed=17)
        self.assertEqual(int(counts.sum()), full_field_size)

        # Round scores to deliberately create ties, as real DK scoring does.
        unique_scores = np.round(rng.normal(75.0, 15.0, size=(sims, unique_count)) * 4.0) / 4.0
        candidate_scores = np.round(rng.normal(80.0, 15.0, size=(sims, candidates)) * 4.0) / 4.0

        left, right = weighted_score_bounds(unique_scores, counts, candidate_scores)

        payout = np.zeros(full_field_size + 1, dtype=np.float64)
        payout[:10] = [250, 150, 100, 75, 50, 40, 30, 30, 25, 25]
        payout[10:20] = 10
        payout[20:50] = 5
        payout[50:100] = 2

        compressed_prizes = tied_prize(left, right, payout)

        # Validate a representative subset by explicitly expanding all duplicate
        # entries. This crosses duplicate expansion, ranking, ties and payout split.
        expanded = np.repeat(unique_scores[:20], counts, axis=1)
        for sim_idx in range(20):
            sorted_scores = np.sort(expanded[sim_idx])
            for cand_idx in range(candidates):
                score = candidate_scores[sim_idx, cand_idx]
                exp_left = int(np.searchsorted(sorted_scores, score, side="left"))
                exp_right = int(np.searchsorted(sorted_scores, score, side="right"))
                expected = tied_prize(
                    np.array([[exp_left]]), np.array([[exp_right]]), payout
                )[0, 0]
                self.assertAlmostEqual(compressed_prizes[sim_idx, cand_idx], expected)

    def test_duplicate_field_rank_percentiles_use_entry_mass_not_unique_rows(self):
        unique_scores = np.array([[100.0, 90.0, 80.0]], dtype=np.float64)
        counts = np.array([100, 10, 1], dtype=np.int64)
        candidate = np.array([[85.0]], dtype=np.float64)
        left, right = weighted_score_bounds(unique_scores, counts, candidate)
        # Candidate beats only the single 80-point entry, not one of three rows.
        greater = counts.sum() - right[0, 0]
        percentile = 1.0 - greater / counts.sum()
        self.assertAlmostEqual(percentile, 1.0 - 110.0 / 111.0)


if __name__ == "__main__":
    unittest.main()
