"""Benchmark production-shaped DK Showdown scoring batch sizes.

Keeps the existing four-worker model and compares only scenario batch size.
Correctness is asserted against the 128-scenario baseline before timings are reported.
"""
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
import os
import numpy as np

from dk_showdown_engine import score_lineup_matrix, weighted_score_bounds

SEED = 20261016
SIMS = 2048
PLAYERS = 36
CANDIDATES = 20
UNIQUE_FIELD = 10547
FIELD_ENTRIES = 47271
WORKERS = 4
BATCH_SIZES = (64, 128, 256, 512)

rng = np.random.default_rng(SEED)
player_scores = rng.normal(10, 7, size=(SIMS, PLAYERS)).astype(np.float32)

def lineups(n):
    out = np.empty((n, 6), dtype=np.int16)
    for i in range(n):
        out[i] = rng.choice(PLAYERS, size=6, replace=False)
    return out

candidate_idx = lineups(CANDIDATES)
field_idx = lineups(UNIQUE_FIELD)
counts = rng.multinomial(FIELD_ENTRIES, np.full(UNIQUE_FIELD, 1.0 / UNIQUE_FIELD)).astype(np.int32)
counts[counts == 0] = 1
# Keep total multiplicity realistic after forcing positive unique counts.
counts[0] += FIELD_ENTRIES - int(counts.sum())
assert counts[0] > 0 and int(counts.sum()) == FIELD_ENTRIES


def run(batch_size):
    ranges = [(i, min(i + batch_size, SIMS)) for i in range(0, SIMS, batch_size)]
    def score_range(bounds):
        start, end = bounds
        sims = player_scores[start:end]
        cand = score_lineup_matrix(sims, candidate_idx)
        field = score_lineup_matrix(sims, field_idx)
        left, right = weighted_score_bounds(field, counts, cand)
        # Preserve portfolio self/tie contribution used by the app.
        pleft = np.sum(cand[:, :, None] < cand[:, None, :], axis=1)
        pright = np.sum(cand[:, :, None] <= cand[:, None, :], axis=1)
        return start, left + pleft, right + pright
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        chunks = list(pool.map(score_range, ranges))
    chunks.sort(key=lambda x: x[0])
    return np.vstack([x[1] for x in chunks]), np.vstack([x[2] for x in chunks])

baseline = run(128)
for batch in BATCH_SIZES:
    actual = run(batch)
    np.testing.assert_array_equal(actual[0], baseline[0])
    np.testing.assert_array_equal(actual[1], baseline[1])

print(f"simulations: {SIMS:,}")
print(f"unique field: {UNIQUE_FIELD:,} / {FIELD_ENTRIES:,} entries")
print(f"portfolio: {CANDIDATES}")
print(f"workers: {WORKERS}")
for batch in BATCH_SIZES:
    timings = []
    for _ in range(3):
        start = perf_counter()
        run(batch)
        timings.append(perf_counter() - start)
    print(f"batch {batch}: {min(timings):.4f} sec")
