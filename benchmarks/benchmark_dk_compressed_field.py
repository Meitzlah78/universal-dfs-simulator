"""Benchmark expanded vs compressed DK Showdown opponent scoring/ranking.

Uses tonight-like dimensions: 47,271 opponent entries, 10,547 unique lineups.
This is a synthetic performance benchmark; correctness is covered by parity tests.
"""
from __future__ import annotations

import time
import numpy as np

from dk_showdown_engine import score_lineup_matrix, weighted_score_bounds


FIELD_SIZE = 47_271
UNIQUE_SIZE = 10_547
N_PLAYERS = 36
N_CANDIDATES = 20
N_SIMS = 256
SEED = 20261016


def _make_unique_lineups(rng: np.random.Generator) -> np.ndarray:
    seen = set()
    rows = []
    while len(rows) < UNIQUE_SIZE:
        captain = int(rng.integers(N_PLAYERS))
        flex = tuple(sorted(rng.choice(
            np.delete(np.arange(N_PLAYERS), captain), size=5, replace=False
        ).tolist()))
        key = (captain, *flex)
        if key not in seen:
            seen.add(key)
            rows.append(key)
    return np.asarray(rows, dtype=np.int16)


def _make_counts(rng: np.random.Generator) -> np.ndarray:
    # Every unique lineup occurs once; distribute the remaining duplicate entries
    # with a heavy-tailed popularity curve to resemble showdown duplication.
    counts = np.ones(UNIQUE_SIZE, dtype=np.int32)
    remaining = FIELD_SIZE - UNIQUE_SIZE
    popularity = rng.pareto(1.5, UNIQUE_SIZE) + 0.05
    popularity /= popularity.sum()
    counts += rng.multinomial(remaining, popularity).astype(np.int32)
    return counts


def _timed(fn, repeats=3):
    samples = []
    value = None
    for _ in range(repeats):
        start = time.perf_counter()
        value = fn()
        samples.append(time.perf_counter() - start)
    return min(samples), value


def main() -> None:
    rng = np.random.default_rng(SEED)
    unique_idx = _make_unique_lineups(rng)
    counts = _make_counts(rng)
    expanded_idx = np.repeat(unique_idx, counts, axis=0)
    candidates = _make_unique_lineups(rng)[:N_CANDIDATES]
    sims = rng.normal(10.0, 8.0, size=(N_SIMS, N_PLAYERS)).astype(np.float32)

    candidate_scores = score_lineup_matrix(sims, candidates[:, 0], candidates[:, 1:])

    def expanded():
        field = score_lineup_matrix(sims, expanded_idx[:, 0], expanded_idx[:, 1:])
        sorted_field = np.sort(field, axis=1)
        right = np.sum(sorted_field[:, :, None] <= candidate_scores[:, None, :], axis=1)
        return right

    def compressed():
        field = score_lineup_matrix(sims, unique_idx[:, 0], unique_idx[:, 1:])
        _, right = weighted_score_bounds(field, counts, candidate_scores)
        return right

    expanded_seconds, expanded_right = _timed(expanded)
    compressed_seconds, compressed_right = _timed(compressed)
    np.testing.assert_array_equal(compressed_right, expanded_right)

    speedup = expanded_seconds / compressed_seconds
    reduction = FIELD_SIZE / UNIQUE_SIZE
    print(f"field entries: {FIELD_SIZE:,}")
    print(f"unique lineups: {UNIQUE_SIZE:,}")
    print(f"row reduction: {reduction:.2f}x")
    print(f"simulations: {N_SIMS:,}")
    print(f"portfolio lineups: {N_CANDIDATES}")
    print(f"expanded seconds: {expanded_seconds:.4f}")
    print(f"compressed seconds: {compressed_seconds:.4f}")
    print(f"measured speedup: {speedup:.2f}x")


if __name__ == "__main__":
    main()
