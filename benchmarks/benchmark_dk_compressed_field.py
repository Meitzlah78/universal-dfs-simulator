"""Benchmark expanded vs compressed DK Showdown opponent scoring/ranking.

Uses tonight-like dimensions: 47,271 opponent entries, 10,547 unique lineups.
Measures 1/2/4 workers and an alternate row-wise NumPy searchsorted rank path.
All timed paths must exactly match expanded-field rank results.
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
    seen, rows = set(), []
    while len(rows) < UNIQUE_SIZE:
        captain = int(rng.integers(N_PLAYERS))
        flex = tuple(sorted(rng.choice(np.delete(np.arange(N_PLAYERS), captain), size=5, replace=False).tolist()))
        key = (captain, *flex)
        if key not in seen:
            seen.add(key); rows.append(key)
    return np.asarray(rows, dtype=np.int16)


def _make_counts(rng: np.random.Generator) -> np.ndarray:
    counts = np.ones(UNIQUE_SIZE, dtype=np.int32)
    popularity = rng.pareto(1.5, UNIQUE_SIZE) + 0.05
    popularity /= popularity.sum()
    counts += rng.multinomial(FIELD_SIZE - UNIQUE_SIZE, popularity).astype(np.int32)
    return counts


def _timed(fn, repeats=3):
    samples, value = [], None
    for _ in range(repeats):
        start = time.perf_counter(); value = fn(); samples.append(time.perf_counter() - start)
    return min(samples), value


def _weighted_bounds_searchsorted(field: np.ndarray, counts: np.ndarray, candidates: np.ndarray):
    """Candidate alternative: C searchsorted per simulation row after one weighted sort."""
    order = np.argsort(field, axis=1, kind="stable")
    sorted_scores = np.take_along_axis(field, order, axis=1)
    cumulative = np.cumsum(counts[order], axis=1, dtype=np.int64)
    left = np.empty(candidates.shape, dtype=np.int64)
    right = np.empty(candidates.shape, dtype=np.int64)
    for row in range(field.shape[0]):
        li = np.searchsorted(sorted_scores[row], candidates[row], side="left")
        ri = np.searchsorted(sorted_scores[row], candidates[row], side="right")
        left[row] = np.where(li > 0, cumulative[row, np.maximum(li - 1, 0)], 0)
        right[row] = np.where(ri > 0, cumulative[row, np.maximum(ri - 1, 0)], 0)
    return left, right


def main() -> None:
    rng = np.random.default_rng(SEED)
    unique_idx = _make_unique_lineups(rng)
    counts = _make_counts(rng)
    expanded_idx = np.repeat(unique_idx, counts, axis=0)
    candidates = _make_unique_lineups(rng)[:N_CANDIDATES]
    sims = rng.normal(10.0, 8.0, size=(N_SIMS, N_PLAYERS)).astype(np.float32)

    def solve(values, field_idx, field_counts, alternate=False):
        candidate_scores = score_lineup_matrix(values, candidates[:, 0], candidates[:, 1:])
        field = score_lineup_matrix(values, field_idx[:, 0], field_idx[:, 1:])
        if field_counts is None:
            sorted_field = np.sort(field, axis=1)
            right = np.sum(sorted_field[:, :, None] <= candidate_scores[:, None, :], axis=1)
        elif alternate:
            _, right = _weighted_bounds_searchsorted(field, field_counts, candidate_scores)
        else:
            _, right = weighted_score_bounds(field, field_counts, candidate_scores)
        return right

    expanded_seconds, expanded_right = _timed(lambda: solve(sims, expanded_idx, None))
    compressed_seconds, compressed_right = _timed(lambda: solve(sims, unique_idx, counts))
    alternate_seconds, alternate_right = _timed(lambda: solve(sims, unique_idx, counts, True))
    np.testing.assert_array_equal(compressed_right, expanded_right)
    np.testing.assert_array_equal(alternate_right, expanded_right)

    worker_results = {}
    alternate_worker_results = {}
    for workers in (1, 2, 4):
        chunks = [chunk for chunk in np.array_split(sims, workers) if len(chunk)]
        def run(alternate=False):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                parts = list(pool.map(lambda values: solve(values, unique_idx, counts, alternate), chunks))
            return np.concatenate(parts, axis=0)
        seconds, right = _timed(run)
        alt_seconds, alt_right = _timed(lambda: run(True))
        np.testing.assert_array_equal(right, expanded_right)
        np.testing.assert_array_equal(alt_right, expanded_right)
        worker_results[workers] = seconds
        alternate_worker_results[workers] = alt_seconds

    print(f"field entries: {FIELD_SIZE:,}")
    print(f"unique lineups: {UNIQUE_SIZE:,}")
    print(f"row reduction: {FIELD_SIZE / UNIQUE_SIZE:.2f}x")
    print(f"expanded seconds: {expanded_seconds:.4f}")
    print(f"current compressed seconds: {compressed_seconds:.4f}")
    print(f"alternate searchsorted seconds: {alternate_seconds:.4f}")
    for workers in (1, 2, 4):
        print(f"current compressed {workers} worker(s): {worker_results[workers]:.4f} sec")
        print(f"alternate searchsorted {workers} worker(s): {alternate_worker_results[workers]:.4f} sec")
    best_current = min(worker_results, key=worker_results.get)
    best_alt = min(alternate_worker_results, key=alternate_worker_results.get)
    print(f"best current workers: {best_current} ({worker_results[best_current]:.4f} sec)")
    print(f"best alternate workers: {best_alt} ({alternate_worker_results[best_alt]:.4f} sec)")
    print(f"best alternate speedup vs expanded: {expanded_seconds / alternate_worker_results[best_alt]:.2f}x")


if __name__ == "__main__":
    main()
