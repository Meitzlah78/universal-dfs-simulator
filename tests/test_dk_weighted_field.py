import numpy as np


def weighted_bounds(unique_scores, counts, candidate_scores):
    order = np.argsort(unique_scores, kind="stable")
    scores = np.asarray(unique_scores)[order]
    weights = np.asarray(counts, dtype=np.int64)[order]
    cumulative = np.cumsum(weights)
    left_i = np.searchsorted(scores, candidate_scores, side="left")
    right_i = np.searchsorted(scores, candidate_scores, side="right")
    left = np.where(left_i > 0, cumulative[left_i - 1], 0)
    right = np.where(right_i > 0, cumulative[right_i - 1], 0)
    return left, right


def average_tied_payout(left, right, payout_by_rank):
    prefix = np.concatenate(([0.0], np.cumsum(np.asarray(payout_by_rank, dtype=np.float64))))
    start = np.asarray(left, dtype=np.int64)
    stop = np.asarray(right, dtype=np.int64) + 1  # candidate itself occupies one tied rank
    return (prefix[stop] - prefix[start]) / (stop - start)


def test_weighted_unique_bounds_equal_expanded_field_searchsorted():
    unique_scores = np.array([77.5, 91.0, 104.25, 88.0], dtype=np.float32)
    counts = np.array([3, 5, 2, 4], dtype=np.int64)
    candidates = np.array([70.0, 77.5, 88.0, 90.0, 91.0, 110.0], dtype=np.float32)
    expanded = np.repeat(unique_scores, counts)
    expanded.sort()
    expected_left = np.searchsorted(expanded, candidates, side="left")
    expected_right = np.searchsorted(expanded, candidates, side="right")
    actual_left, actual_right = weighted_bounds(unique_scores, counts, candidates)
    np.testing.assert_array_equal(actual_left, expected_left)
    np.testing.assert_array_equal(actual_right, expected_right)


def test_weighted_unique_bounds_preserve_tie_width():
    unique_scores = np.array([100.0, 90.0, 100.0], dtype=np.float32)
    counts = np.array([7, 2, 5], dtype=np.int64)
    left, right = weighted_bounds(unique_scores, counts, np.array([100.0], dtype=np.float32))
    assert left[0] == 2
    assert right[0] == 14
    assert right[0] - left[0] == 12


def test_weighted_unique_field_preserves_tie_aware_payout():
    unique_scores = np.array([120.0, 110.0, 100.0, 95.0], dtype=np.float32)
    counts = np.array([1, 3, 4, 2], dtype=np.int64)
    candidate = np.array([110.0], dtype=np.float32)
    payout = np.array([100.0, 50.0, 30.0, 20.0, 10.0, 8.0, 6.0, 4.0, 2.0, 1.0, 0.0])

    expanded = np.repeat(unique_scores, counts)
    expanded.sort()
    expected_left = np.searchsorted(expanded, candidate, side="left")
    expected_right = np.searchsorted(expanded, candidate, side="right")
    expected = average_tied_payout(expected_left, expected_right, payout)

    left, right = weighted_bounds(unique_scores, counts, candidate)
    actual = average_tied_payout(left, right, payout)
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=0.0)
