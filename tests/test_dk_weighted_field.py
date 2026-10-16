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
