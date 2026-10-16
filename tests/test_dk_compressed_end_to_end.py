import numpy as np

from dk_showdown_engine import score_lineup_matrix, weighted_score_bounds


def _expanded_bounds(field_scores, candidate_scores):
    sorted_scores = np.sort(field_scores, axis=1)
    left = np.sum(sorted_scores[:, :, None] < candidate_scores[:, None, :], axis=1)
    right = np.sum(sorted_scores[:, :, None] <= candidate_scores[:, None, :], axis=1)
    return left, right


def test_compressed_opponent_bounds_match_expanded_field_across_simulations():
    rng = np.random.default_rng(20261016)
    sims = rng.normal(10.0, 6.0, size=(31, 9)).astype(np.float32)

    # Canonical DK Showdown rows: captain first, five FLEX players.
    unique_idx = np.array([
        [0, 1, 2, 3, 4, 5],
        [1, 0, 2, 3, 4, 6],
        [2, 0, 1, 3, 5, 7],
        [3, 0, 1, 2, 6, 8],
    ], dtype=np.int16)
    counts = np.array([7, 3, 11, 5], dtype=np.int32)
    candidates = np.array([
        [0, 1, 2, 3, 4, 5],  # exact field lineup, exercises ties
        [4, 0, 1, 2, 6, 8],
        [5, 0, 1, 3, 6, 7],
    ], dtype=np.int16)

    unique_scores = score_lineup_matrix(sims, unique_idx[:, 0], unique_idx[:, 1:])
    candidate_scores = score_lineup_matrix(sims, candidates[:, 0], candidates[:, 1:])

    expanded_idx = np.repeat(unique_idx, counts, axis=0)
    expanded_scores = score_lineup_matrix(sims, expanded_idx[:, 0], expanded_idx[:, 1:])
    expected_left, expected_right = _expanded_bounds(expanded_scores, candidate_scores)
    actual_left, actual_right = weighted_score_bounds(unique_scores, counts, candidate_scores)

    np.testing.assert_array_equal(actual_left, expected_left)
    np.testing.assert_array_equal(actual_right, expected_right)


def test_full_contest_rank_inputs_match_expanded_semantics_with_portfolio_ties():
    # Hand-built scores include opponent duplicates, equal-score unique rows,
    # portfolio ties, and each candidate's self-entry in the <= boundary.
    unique_field = np.array([[10.0, 20.0, 20.0, 30.0]], dtype=np.float32)
    multiplicity = np.array([4, 2, 3, 1], dtype=np.int32)
    portfolio = np.array([[20.0, 20.0, 25.0]], dtype=np.float32)

    field_left, field_right = weighted_score_bounds(unique_field, multiplicity, portfolio)
    portfolio_left = np.sum(portfolio[:, :, None] < portfolio[:, None, :], axis=1)
    portfolio_right = np.sum(portfolio[:, :, None] <= portfolio[:, None, :], axis=1)
    compressed_left = field_left + portfolio_left
    compressed_right = field_right + portfolio_right

    expanded_field = np.repeat(unique_field[0], multiplicity)[None, :]
    combined = np.concatenate([expanded_field, portfolio], axis=1)
    expected_left, expected_right = _expanded_bounds(combined, portfolio)

    np.testing.assert_array_equal(compressed_left, expected_left)
    np.testing.assert_array_equal(compressed_right, expected_right)

    search_field_size = combined.shape[1]
    expected_greater = search_field_size - expected_right
    compressed_greater = search_field_size - compressed_right
    np.testing.assert_array_equal(compressed_greater, expected_greater)

    comparison_field_size = expanded_field.shape[1] + portfolio.shape[1] - 1
    expected_pct = 1.0 - expected_greater / comparison_field_size
    compressed_pct = 1.0 - compressed_greater / comparison_field_size
    np.testing.assert_allclose(compressed_pct, expected_pct, rtol=0, atol=0)
