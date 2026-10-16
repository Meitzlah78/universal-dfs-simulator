"""Benchmark production-shaped DK Showdown scoring batch sizes.

Keeps the existing four-worker model and compares only scenario batch size.
Correctness is asserted against the 128-scenario baseline before timings are reported.
"""
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
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
# Every compressed row must have positive multiplicity. Allocate one entry to
# each unique lineup first, then distribute the remaining field entries.
counts = np.ones(UNIQUE_FIELD, dtype=np.int32)
counts += rng.multinomial(
    FIELD_ENTRIES - UNIQUE_FIELD,
    np.full(UNIQUE_FIELD, 1.0 / UNIQUE_FIELD),
).astype(np.int32)
assert np.all(counts > 0) and int(counts.sum()) == FIELD_ENTRIES


def score_compact(sims, lineup_idx):
    """Call the production scorer using compact [CPT, FLEX1..5] indices."""
    return score_lineup_matrix(sims, lineup_idx[:, 0], lineup_idx[:, 1:])


def run(batch_size):
    ranges = [(i, min(i + batch_size, SIMS)) for i in range(0, SIMS, batch_size)]
    def score_range(bounds):
        start, end = bounds
        sims = player_scores[start:end]
        cand = score_compact(sims, candidate_idx)
        field = score_compact(sims, field_idx)
        left, right = weighted_score_bounds(field, counts, cand)
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
