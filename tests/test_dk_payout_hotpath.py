import numpy as np


def payout_from_prefix(estimated_ranks, estimated_tie_sizes, payout_schedule, field_size):
    tie_start = np.maximum(
        1,
        np.floor(estimated_ranks - (estimated_tie_sizes - 1) / 2.0).astype(np.int64),
    )
    tie_end = np.minimum(field_size, tie_start + estimated_tie_sizes - 1)
    prefix = np.concatenate(([0.0], np.cumsum(np.asarray(payout_schedule, dtype=np.float64))))
    safe_start = np.clip(tie_start - 1, 0, len(payout_schedule))
    safe_end = np.clip(tie_end, 0, len(payout_schedule))
    sums = prefix[safe_end] - prefix[safe_start]
    return np.divide(sums, estimated_tie_sizes, out=np.zeros_like(sums), where=estimated_tie_sizes > 0)


def payout_by_expanding_ranks(estimated_ranks, estimated_tie_sizes, payout_schedule, field_size):
    payout = np.asarray(payout_schedule, dtype=np.float64)
    out = np.zeros_like(estimated_ranks, dtype=np.float64)
    for row in range(estimated_ranks.shape[0]):
        for col in range(estimated_ranks.shape[1]):
            tie_size = int(estimated_tie_sizes[row, col])
            start = max(1, int(np.floor(estimated_ranks[row, col] - (tie_size - 1) / 2.0)))
            end = min(field_size, start + tie_size - 1)
            total = 0.0
            for rank in range(start, end + 1):
                if rank <= len(payout):
                    total += payout[rank - 1]
            out[row, col] = total / tie_size
    return out


def test_prefix_payout_matches_explicit_rank_expansion():
    ranks = np.array([[1.0, 2.4, 4.8, 8.2], [1.7, 5.0, 9.9, 12.0]], dtype=np.float64)
    ties = np.array([[1, 2, 5, 4], [3, 1, 6, 8]], dtype=np.int64)
    payout = np.array([250, 150, 100, 75, 50, 40, 30, 30, 25, 25, 20, 20], dtype=np.float64)
    expected = payout_by_expanding_ranks(ranks, ties, payout, field_size=20)
    actual = payout_from_prefix(ranks, ties, payout, field_size=20)
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=0.0)


def test_prefix_payout_preserves_ties_crossing_cash_line():
    ranks = np.array([[9.5]], dtype=np.float64)
    ties = np.array([[6]], dtype=np.int64)
    payout = np.array([100, 50, 30, 20, 10, 8, 6, 4, 2, 1], dtype=np.float64)
    expected = payout_by_expanding_ranks(ranks, ties, payout, field_size=20)
    actual = payout_from_prefix(ranks, ties, payout, field_size=20)
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=0.0)
    # The six-way tie occupies ranks 7-12. Ranks 11-12 are unpaid, so the
    # available prizes at 7-10 are shared across all six tied entries.
    assert actual[0, 0] == (6.0 + 4.0 + 2.0 + 1.0) / 6.0


def test_prefix_payout_handles_ties_beyond_schedule():
    ranks = np.array([[18.0, 25.0]], dtype=np.float64)
    ties = np.array([[10, 7]], dtype=np.int64)
    payout = np.array([100, 50, 25, 10, 5], dtype=np.float64)
    expected = payout_by_expanding_ranks(ranks, ties, payout, field_size=30)
    actual = payout_from_prefix(ranks, ties, payout, field_size=30)
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=0.0)
