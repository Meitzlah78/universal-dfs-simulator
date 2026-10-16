"""DraftKings Showdown engine primitives.

This module is intentionally UI-free.  The first refactor stage moves stable,
behavior-preserving Showdown calculations here so they can be tested and
optimized independently from Streamlit and FanDuel code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


DK_SHOWDOWN_SALARY_CAP = 50_000
DK_CAPTAIN_SALARY_MULTIPLIER = 1.5
DK_CAPTAIN_POINTS_MULTIPLIER = 1.5
DK_FLEX_COUNT = 5


@dataclass(frozen=True)
class ShowdownRules:
    salary_cap: int = DK_SHOWDOWN_SALARY_CAP
    flex_count: int = DK_FLEX_COUNT
    captain_salary_multiplier: float = DK_CAPTAIN_SALARY_MULTIPLIER
    captain_points_multiplier: float = DK_CAPTAIN_POINTS_MULTIPLIER


def lineup_key(captain: str, flex: Iterable[str]) -> tuple[str, tuple[str, ...]]:
    """Canonical exact-lineup key: Captain is distinct; FLEX order is not."""
    return str(captain), tuple(sorted(str(player) for player in flex))


def lineup_salary(
    captain_index: int,
    flex_indices: Sequence[int],
    salaries: np.ndarray,
    rules: ShowdownRules = ShowdownRules(),
) -> int:
    """Return DK Showdown salary using the existing 1.5x Captain salary rule."""
    captain_salary = float(salaries[int(captain_index)]) * rules.captain_salary_multiplier
    flex_salary = float(np.sum(salaries[np.asarray(flex_indices, dtype=int)]))
    return int(round(captain_salary + flex_salary))


def score_lineup_matrix(
    simulation_values: np.ndarray,
    captain_indices: np.ndarray,
    flex_indices: np.ndarray,
    rules: ShowdownRules = ShowdownRules(),
) -> np.ndarray:
    """Vectorized scenario scores for many DK Showdown lineups.

    simulation_values shape: scenarios x players
    captain_indices shape: lineups
    flex_indices shape: lineups x 5
    Returns: scenarios x lineups
    """
    values = np.asarray(simulation_values, dtype=float)
    captains = np.asarray(captain_indices, dtype=int)
    flex = np.asarray(flex_indices, dtype=int)
    if flex.ndim != 2 or flex.shape[1] != rules.flex_count:
        raise ValueError(f"flex_indices must have shape (n, {rules.flex_count})")
    captain_scores = values[:, captains] * rules.captain_points_multiplier
    flex_scores = np.take(values, flex, axis=1).sum(axis=2)
    return captain_scores + flex_scores


def exact_duplicate_counts(lineups: pd.DataFrame) -> pd.Series:
    """Count exact DK Showdown constructions while ignoring FLEX slot order."""
    required = ["Captain"] + [f"Flex{i}" for i in range(1, DK_FLEX_COUNT + 1)]
    missing = [column for column in required if column not in lineups.columns]
    if missing:
        raise ValueError(f"Missing Showdown columns: {missing}")
    keys = [
        lineup_key(row["Captain"], [row[f"Flex{i}"] for i in range(1, DK_FLEX_COUNT + 1)])
        for _, row in lineups[required].iterrows()
    ]
    counts = pd.Series(keys).value_counts()
    return pd.Series([int(counts[key]) for key in keys], index=lineups.index, dtype=int)
