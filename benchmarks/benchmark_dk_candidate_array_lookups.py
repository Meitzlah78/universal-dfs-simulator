"""Benchmark removing Python dict/list-comprehension work from DK candidate batches.

Compares the current name-based salary/team construction with precomputed numeric
arrays indexed by sampled FLEX indices. Exact salary/team validity parity is required.
"""
from time import perf_counter
import numpy as np

SEED = 20261016
ROWS = 100_000
PLAYERS = 32
FLEX = 5
rng = np.random.default_rng(SEED)

names = np.asarray([f"P{i}" for i in range(PLAYERS)], dtype=object)
salary_values = rng.integers(200, 12000, size=PLAYERS, dtype=np.int32)
team_values = rng.integers(0, 2, size=PLAYERS, dtype=np.int8)
salary_map = {str(names[i]): int(salary_values[i]) for i in range(PLAYERS)}
team_map = {str(names[i]): str(int(team_values[i])) for i in range(PLAYERS)}

captain = 0
flex_names = names[1:]
flex_salary_values = salary_values[1:]
flex_team_values = team_values[1:]
sampled_indices = np.empty((ROWS, FLEX), dtype=np.int16)
for row in range(ROWS):
    sampled_indices[row] = rng.choice(len(flex_names), size=FLEX, replace=False)


def current_path():
    sampled_names = flex_names[sampled_indices]
    sampled_salaries = np.asarray(
        [[int(salary_map.get(str(name), 0)) for name in row] for row in sampled_names],
        dtype=np.int32,
    )
    sampled_teams = np.asarray(
        [[str(team_map.get(str(name), "")) for name in row] for row in sampled_names],
        dtype=object,
    )
    salary = int(salary_values[captain] * 1.5) + sampled_salaries.sum(axis=1, dtype=np.int32)
    both_teams = np.any(sampled_teams != str(int(team_values[captain])), axis=1)
    return salary, both_teams


def indexed_path():
    salary = int(salary_values[captain] * 1.5) + flex_salary_values[sampled_indices].sum(axis=1, dtype=np.int32)
    both_teams = np.any(flex_team_values[sampled_indices] != team_values[captain], axis=1)
    return salary, both_teams

expected = current_path()
actual = indexed_path()
np.testing.assert_array_equal(actual[0], expected[0])
np.testing.assert_array_equal(actual[1], expected[1])


def best(fn):
    timings = []
    for _ in range(5):
        start = perf_counter()
        fn()
        timings.append(perf_counter() - start)
    return min(timings)

current = best(current_path)
indexed = best(indexed_path)
print(f"rows: {ROWS:,}")
print(f"current name/dict lookups: {current:.4f} sec")
print(f"precomputed numeric arrays: {indexed:.4f} sec")
print(f"speedup: {current / indexed:.2f}x")
