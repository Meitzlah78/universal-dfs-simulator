"""Benchmark DK portfolio < / <= bounds used after weighted opponent ranking.

The production portfolio is normally 20 lineups, but this also checks larger
candidate counts so we do not optimize the wrong hot path. Every candidate
method must exactly match the current broadcast semantics.
"""
from __future__ import annotations

import time
import numpy as np

SEED = 20261016
N_SIMS = 256


def _timed(fn, repeats=5):
    best = float("inf")
    value = None
    for _ in range(repeats):
        start = time.perf_counter()
        value = fn()
        best = min(best, time.perf_counter() - start)
    return best, value


def broadcast_bounds(scores: np.ndarray):
    left = np.sum(scores[:, :, None] < scores[:, None, :], axis=1)
    right = np.sum(scores[:, :, None] <= scores[:, None, :], axis=1)
    return left, right


def row_searchsorted_bounds(scores: np.ndarray):
    left = np.empty(scores.shape, dtype=np.int64)
    right = np.empty(scores.shape, dtype=np.int64)
    for row in range(scores.shape[0]):
        sorted_row = np.sort(scores[row])
        left[row] = np.searchsorted(sorted_row, scores[row], side="left")
        right[row] = np.searchsorted(sorted_row, scores[row], side="right")
    return left, right


def argsort_bounds(scores: np.ndarray):
    # Vectorized sort plus row-wise C search. This avoids the simulations x N x N
    # boolean temporaries created by the current broadcast implementation.
    sorted_scores = np.sort(scores, axis=1)
    left = np.empty(scores.shape, dtype=np.int64)
    right = np.empty(scores.shape, dtype=np.int64)
    for row in range(scores.shape[0]):
        left[row] = np.searchsorted(sorted_scores[row], scores[row], side="left")
        right[row] = np.searchsorted(sorted_scores[row], scores[row], side="right")
    return left, right


def main():
    rng = np.random.default_rng(SEED)
    for n_candidates in (20, 100, 500, 2500):
        scores = rng.normal(90.0, 18.0, size=(N_SIMS, n_candidates)).astype(np.float32)
        # Force realistic exact-score ties.
        if n_candidates >= 20:
            scores[:, 1] = scores[:, 0]
            scores[:, 7] = scores[:, 6]

        base_sec, expected = _timed(lambda: broadcast_bounds(scores))
        row_sec, row_actual = _timed(lambda: row_searchsorted_bounds(scores))
        sort_sec, sort_actual = _timed(lambda: argsort_bounds(scores))
        np.testing.assert_array_equal(row_actual[0], expected[0])
        np.testing.assert_array_equal(row_actual[1], expected[1])
        np.testing.assert_array_equal(sort_actual[0], expected[0])
        np.testing.assert_array_equal(sort_actual[1], expected[1])

        print(f"candidates={n_candidates:,}")
        print(f"  broadcast: {base_sec:.6f} sec")
        print(f"  row searchsorted: {row_sec:.6f} sec")
        print(f"  sorted searchsorted: {sort_sec:.6f} sec")
        print(f"  row speedup: {base_sec / row_sec:.2f}x")
        print(f"  sorted speedup: {base_sec / sort_sec:.2f}x")


if __name__ == "__main__":
    main()
