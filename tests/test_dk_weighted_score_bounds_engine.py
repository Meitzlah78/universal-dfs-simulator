import numpy as np

from dk_showdown_engine import weighted_score_bounds


def test_weighted_score_bounds_match_expanded_field_across_simulations():
    unique = np.array([
        [80.0, 90.0, 100.0, 90.0],
        [105.0, 95.0, 95.0, 70.0],
        [50.0, 60.0, 70.0, 80.0],
    ], dtype=np.float32)
    counts = np.array([3, 5, 2, 4], dtype=np.int64)
    candidates = np.array([
        [90.0, 99.0],
        [95.0, 110.0],
        [49.0, 80.0],
    ], dtype=np.float32)

    left, right = weighted_score_bounds(unique, counts, candidates)
    for sim in range(len(unique)):
        expanded = np.repeat(unique[sim], counts)
        expanded.sort()
        np.testing.assert_array_equal(left[sim], np.searchsorted(expanded, candidates[sim], side="left"))
        np.testing.assert_array_equal(right[sim], np.searchsorted(expanded, candidates[sim], side="right"))


def test_weighted_score_bounds_reject_bad_multiplicities():
    scores = np.ones((2, 3), dtype=np.float32)
    candidates = np.ones((2, 1), dtype=np.float32)
    for counts in (np.array([1, 2]), np.array([1, 0, 2])):
        try:
            weighted_score_bounds(scores, counts, candidates)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected invalid multiplicities to be rejected")
