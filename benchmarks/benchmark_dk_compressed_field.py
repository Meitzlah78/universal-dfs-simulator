"""Benchmark expanded vs compressed DK Showdown opponent scoring/ranking.

Uses tonight-like dimensions: 47,271 opponent entries, 10,547 unique lineups.
Also measures the compressed hot path with 1, 2, and 4 Python workers.
This is a synthetic performance benchmark; correctness is covered by parity tests.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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

    def solve(values: np.ndarray, field_idx: np.ndarray, field_counts: np.ndarray | None):
        candidate_scores = score_lineup_matrix(values, candidates[:, 0], candidates[:, 1:])
        field = score_lineup_matrix(values, field_idx[:, 0], field_idx[:, 1:])
        if field_counts is None:
            sorted_field = np.sort(field, axis=1)
            right = np.sum(sorted_field[:, :, None] <= candidate_scores[:, None, :], axis=1)
        else:
            _, right = weighted_score_bounds(field, field_counts, candidate_scores)
        return right

    def expanded():
        return solve(sims, expanded_idx, None)

    def compressed():
        return solve(sims, unique_idx, counts)

    def compressed_workers(workers: int):
        chunks = [chunk for chunk in np.array_split(sims, workers) if len(chunk)]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(lambda values: solve(values, unique_idx, counts), chunks))
        return np.concatenate(parts, axis=0)

    expanded_seconds, expanded_right = _timed(expanded)
    compressed_seconds, compressed_right = _timed(compressed)
    np.testing.assert_array_equal(compressed_right, expanded_right)

    worker_results = {}
    for workers in (1, 2, 4):
        seconds, right = _timed(lambda w=workers: compressed_workers(w))
        np.testing.assert_array_equal(right, expanded_right)
        worker_results[workers] = seconds

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
    for workers, seconds in worker_results.items():
        print(f"compressed {workers} worker(s): {seconds:.4f} sec")
    best_workers = min(worker_results, key=worker_results.get)
    print(f"best worker count: {best_workers}")
    print(f"best worker speedup vs expanded: {expanded_seconds / worker_results[best_workers]:.2f}x")


if __name__ == "__main__":
    main()
