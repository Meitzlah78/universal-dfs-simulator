"""Memory-bounded exhaustive DraftKings Showdown candidate enumeration."""

from __future__ import annotations

import heapq
import itertools
from typing import Callable

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
    """Examine every CPT + five-FLEX construction while retaining only top K.

    This is exhaustive over the supplied player pool but memory bounded: legal
    lineups are scored as they are encountered and only the strongest ``keep``
    records are retained. CPT salary is 1.5x. Flex combinations are generated
    in C rather than materialized as millions of Python/DataFrame rows.
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
            if require_two_teams:
                lineup_teams = {teams[captain], *(teams[i] for i in flex)}
                if len(lineup_teams) < 2:
                    continue
            legal += 1
            score = float(score_fn(captain, flex))
            item = (score, (captain, flex))
            if len(heap) < keep:
                heapq.heappush(heap, item)
            elif score > heap[0][0]:
                heapq.heapreplace(heap, item)

    retained = sorted(heap, key=lambda item: item[0], reverse=True)
    rows = []
    for score, (captain, flex) in retained:
        row = {
            "Captain": names[captain],
            **{f"Flex{i + 1}": names[player] for i, player in enumerate(flex)},
            "CandidateScore": score,
            "Salary": int(round(float(salaries[captain]) * 1.5)) + int(salaries[list(flex)].sum()),
        }
        rows.append(row)
    result = pd.DataFrame(rows)
    result.attrs["examined_lineups"] = examined
    result.attrs["legal_lineups"] = legal
    result.attrs["retained_lineups"] = len(result)
    return result
