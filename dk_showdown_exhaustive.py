"""Memory-bounded exhaustive DraftKings Showdown candidate enumeration."""

from __future__ import annotations

import heapq
import itertools
from typing import Callable, Mapping

import numpy as np
import pandas as pd


def exhaustive_showdown_candidates(
    players: pd.DataFrame,
    score_fn: Callable[[int, tuple[int, ...]], float],
    keep: int = 5000,
    salary_cap: int = 50000,
    salary_floor: int = 0,
    require_two_teams: bool = True,
) -> pd.DataFrame:
    """Examine every CPT + five-FLEX construction while retaining only top K."""
    required = {"Name", "Salary", "Team"}
    missing = required.difference(players.columns)
    if missing:
        raise KeyError("missing player columns: " + ", ".join(sorted(missing)))
    if keep < 1:
        raise ValueError("keep must be positive")

    clean = players.reset_index(drop=True).copy()
    names = clean["Name"].astype(str).to_numpy()
    teams = clean["Team"].astype(str).to_numpy()
    salaries = pd.to_numeric(clean["Salary"], errors="raise").to_numpy(dtype=np.int64)
    n = len(clean)
    if n < 6:
        raise ValueError("Showdown requires at least six players")

    heap: list[tuple[float, tuple[int, tuple[int, ...]]]] = []
    examined = legal = 0
    all_indices = tuple(range(n))
    for captain in all_indices:
        flex_pool = all_indices[:captain] + all_indices[captain + 1 :]
        captain_salary = int(round(float(salaries[captain]) * 1.5))
        for flex in itertools.combinations(flex_pool, 5):
            examined += 1
            salary = captain_salary + int(salaries[list(flex)].sum())
            if salary > salary_cap or salary < salary_floor:
                continue
            if require_two_teams and len({teams[captain], *(teams[i] for i in flex)}) < 2:
                continue
            legal += 1
            score = float(score_fn(captain, flex))
            item = (score, (captain, flex))
            if len(heap) < keep:
                heapq.heappush(heap, item)
            elif score > heap[0][0]:
                heapq.heapreplace(heap, item)

    return _heap_to_frame(heap, names, salaries, examined, legal)


def fast_exhaustive_showdown_candidates(
    players: pd.DataFrame,
    player_sim: Mapping[str, Mapping[str, float]],
    ownership_proxy: Mapping[str, float],
    keep: int = 5000,
    salary_cap: int = 50000,
    salary_floor: int = 0,
    p95_weight: float = 0.30,
    p99_weight: float = 0.55,
    mean_weight: float = 0.15,
    stddev_weight: float = 0.10,
    require_two_teams: bool = True,
) -> pd.DataFrame:
    """Exhaustively prescreen Showdown lineups using vectorized captain batches.

    Each captain's entire five-FLEX combination space is built as compact integer
    arrays, filtered and scored with NumPy, then only that captain batch's best K
    is merged into a global K-sized heap. This avoids millions of Python score
    calls and never materializes the full lineup universe as a DataFrame.
    """
    required = {"Name", "Salary", "Team"}
    missing = required.difference(players.columns)
    if missing:
        raise KeyError("missing player columns: " + ", ".join(sorted(missing)))
    if keep < 1:
        raise ValueError("keep must be positive")

    clean = players.reset_index(drop=True).copy()
    names = clean["Name"].astype(str).to_numpy()
    teams = clean["Team"].astype(str).to_numpy()
    salaries = pd.to_numeric(clean["Salary"], errors="raise").to_numpy(dtype=np.int64)
    n = len(clean)
    if n < 6:
        raise ValueError("Showdown requires at least six players")

    def metric(key: str) -> np.ndarray:
        return np.asarray([float(player_sim[str(name)].get(key, 0.0)) for name in names], dtype=np.float64)

    mean, p95, p99, std = metric("Mean"), metric("P95"), metric("P99"), metric("StdDev")
    own = np.asarray([float(ownership_proxy.get(str(name), 0.0)) for name in names], dtype=np.float64)
    heap: list[tuple[float, tuple[int, tuple[int, ...]]]] = []
    examined = legal = 0
    all_indices = np.arange(n, dtype=np.int32)

    for captain in range(n):
        flex_pool = all_indices[all_indices != captain]
        combos = np.fromiter(
            (i for combo in itertools.combinations(flex_pool.tolist(), 5) for i in combo),
            dtype=np.int32,
        ).reshape(-1, 5)
        examined += len(combos)
        total_salary = int(round(float(salaries[captain]) * 1.5)) + salaries[combos].sum(axis=1)
        mask = (total_salary <= salary_cap) & (total_salary >= salary_floor)
        if require_two_teams:
            same_team = np.all(teams[combos] == teams[captain], axis=1)
            mask &= ~same_team
        combos = combos[mask]
        if not len(combos):
            continue
        legal += len(combos)

        total_mean = mean[captain] * 1.5 + mean[combos].sum(axis=1)
        total_p95 = p95[captain] * 1.5 + p95[combos].sum(axis=1)
        total_p99 = p99[captain] * 1.5 + p99[combos].sum(axis=1)
        total_std = std[captain] * 1.5 + std[combos].sum(axis=1)
        raw = total_p95 * p95_weight + total_p99 * p99_weight + total_mean * mean_weight + total_std * stddev_weight
        lineup_own = own[captain] * 1.5 + own[combos].sum(axis=1)
        ownership_tax = np.maximum(0.0, lineup_own - 15.0 * 6.5) * 0.06
        upside_credit = np.minimum(ownership_tax * 0.35, np.maximum(0.0, total_p99 - total_p95) * 0.03)
        scores = raw - ownership_tax + upside_credit

        take = min(keep, len(scores))
        best_local = np.argpartition(scores, -take)[-take:] if take < len(scores) else np.arange(len(scores))
        for idx in best_local:
            flex = tuple(int(x) for x in combos[idx])
            item = (float(scores[idx]), (captain, flex))
            if len(heap) < keep:
                heapq.heappush(heap, item)
            elif item[0] > heap[0][0]:
                heapq.heapreplace(heap, item)

    return _heap_to_frame(heap, names, salaries, examined, legal)


def _heap_to_frame(heap, names, salaries, examined: int, legal: int) -> pd.DataFrame:
    retained = sorted(heap, key=lambda item: item[0], reverse=True)
    rows = []
    for score, (captain, flex) in retained:
        rows.append({
            "Captain": names[captain],
            **{f"Flex{i + 1}": names[player] for i, player in enumerate(flex)},
            "CandidateScore": score,
            "Salary": int(round(float(salaries[captain]) * 1.5)) + int(salaries[list(flex)].sum()),
        })
    result = pd.DataFrame(rows)
    result.attrs["examined_lineups"] = int(examined)
    result.attrs["legal_lineups"] = int(legal)
    result.attrs["retained_lineups"] = len(result)
    return result
