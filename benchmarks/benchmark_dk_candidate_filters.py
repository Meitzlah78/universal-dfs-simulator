"""Benchmark the Python candidate rejection loop against vectorized batch filters.

This isolates only rules that can be applied before candidate scoring: salary range,
locked-player inclusion, and both-team requirement. It deliberately does not change
sampling, duplicate suppression, or scoring semantics.
"""
from time import perf_counter
import numpy as np

SEED = 20261016
ROWS = 100_000
PLAYERS = 32
FLEX = 5
MIN_SALARY = 40_000
MAX_SALARY = 50_000

rng = np.random.default_rng(SEED)
salaries = rng.integers(200, 12_001, size=PLAYERS, dtype=np.int32)
teams = rng.integers(0, 2, size=PLAYERS, dtype=np.int8)
captain = 3
captain_salary = int(np.ceil(salaries[captain] * 1.5 / 100.0) * 100)
locked = np.array([2, 11], dtype=np.int16)

# Produce valid five-player FLEX samples excluding the captain.
pool = np.array([i for i in range(PLAYERS) if i != captain], dtype=np.int16)
noise = rng.random((ROWS, len(pool)), dtype=np.float32)
idx = np.argpartition(noise, FLEX, axis=1)[:, :FLEX]
sampled = pool[idx]


def python_filter(rows):
    out = np.zeros(len(rows), dtype=bool)
    for i, flex in enumerate(rows):
        lineup = [captain] + [int(x) for x in flex]
        if not all(int(p) in lineup for p in locked):
            continue
        total_salary = captain_salary + sum(int(salaries[int(p)]) for p in flex)
        if total_salary < MIN_SALARY or total_salary > MAX_SALARY:
            continue
        lineup_teams = {int(teams[p]) for p in lineup}
        if len(lineup_teams) < 2:
            continue
        out[i] = True
    return out


def vector_filter(rows):
    total_salary = captain_salary + salaries[rows].sum(axis=1, dtype=np.int32)
    valid = (total_salary >= MIN_SALARY) & (total_salary <= MAX_SALARY)

    if locked.size:
        captain_locked = locked == captain
        flex_has_locked = (rows[:, :, None] == locked[None, None, :]).any(axis=1)
        valid &= np.all(flex_has_locked | captain_locked[None, :], axis=1)

    captain_team = teams[captain]
    flex_teams = teams[rows]
    valid &= np.any(flex_teams != captain_team, axis=1)
    return valid


# Correctness first.
expected = python_filter(sampled)
actual = vector_filter(sampled)
np.testing.assert_array_equal(actual, expected)

# Warm up and take the best of repeated timings to reduce runner noise.
def best_time(fn, repeats=5):
    best = float("inf")
    for _ in range(repeats):
        start = perf_counter()
        fn(sampled)
        best = min(best, perf_counter() - start)
    return best

py_seconds = best_time(python_filter, 3)
vec_seconds = best_time(vector_filter, 5)
print(f"candidate rows: {ROWS:,}")
print(f"accepted rows: {int(actual.sum()):,}")
print(f"python filters: {py_seconds:.6f} sec")
print(f"vector filters: {vec_seconds:.6f} sec")
print(f"speedup: {py_seconds / vec_seconds:.2f}x")
