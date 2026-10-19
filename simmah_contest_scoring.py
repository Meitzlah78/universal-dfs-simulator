"""Numeric helpers for exact contest score ranks."""
import numpy as np


def score_insertion_bounds(sorted_scores, candidate_scores):
    """Return left/right insertion ranks per simulation, including all ties.

    NumPy searches each contiguous row in compiled code. This avoids allocating
    full simulation-by-candidate work arrays at every binary-search step.
    """
    sorted_scores = np.asarray(sorted_scores)
    candidate_scores = np.asarray(candidate_scores)
    if sorted_scores.ndim != 2 or candidate_scores.ndim != 2:
        raise ValueError('Contest score arrays must be two-dimensional')
    if sorted_scores.shape[0] != candidate_scores.shape[0]:
        raise ValueError('Contest score arrays must have matching simulation counts')
    left = np.empty(candidate_scores.shape, dtype=np.int64)
    right = np.empty(candidate_scores.shape, dtype=np.int64)
    for row in range(len(sorted_scores)):
        left[row] = np.searchsorted(sorted_scores[row], candidate_scores[row], side='left')
        right[row] = np.searchsorted(sorted_scores[row], candidate_scores[row], side='right')
    return left, right
