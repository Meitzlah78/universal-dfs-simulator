import numpy as np
from dk_showdown_engine import weighted_score_bounds


def test_weighted_field_plus_portfolio_matches_expanded_comparison_counts():
    # One simulation row: unique opponent scores with heavy duplicate multiplicity.
    field_scores = np.array([[70.0, 80.0, 90.0, 100.0]])
    counts = np.array([3, 7, 5, 2], dtype=np.int64)
    portfolio = np.array([[80.0, 90.0, 95.0]])
    expanded = np.repeat(field_scores[0], counts)

    # Engine returns opponent counts strictly below and <= candidate score.
    field_left, field_right = weighted_score_bounds(field_scores, counts, portfolio)

    for i, score in enumerate(portfolio[0]):
        other_portfolio = np.delete(portfolio[0], i)
        comparison = np.concatenate((expanded, other_portfolio))
        expected_left = np.searchsorted(np.sort(comparison), score, side="left")
        expected_right = np.searchsorted(np.sort(comparison), score, side="right")

        # Add the other portfolio entries to weighted opponent boundaries.
        actual_left = field_left[0, i] + np.count_nonzero(other_portfolio < score)
        actual_right = field_right[0, i] + np.count_nonzero(other_portfolio <= score)
        assert actual_left == expected_left
        assert actual_right == expected_right

        expected_greater = len(comparison) - expected_right
        actual_greater = len(comparison) - actual_right
        assert actual_greater == expected_greater
        assert (actual_right - actual_left) == np.count_nonzero(comparison == score)
