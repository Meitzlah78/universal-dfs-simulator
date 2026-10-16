"""Post-contest-sim portfolio selection helpers.

Candidate generation and contest simulation happen before this module is used.
Diversification only selects from already-scored lineups; it never changes or
filters the 5,000-lineup candidate build.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import pandas as pd


SHOWDOWN_SLOTS = ("Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5")


def _lineup_players(row: pd.Series, lineup_columns: Sequence[str]) -> frozenset[str]:
    return frozenset(str(row[column]) for column in lineup_columns)


def min_unique_players(a: Iterable[str], b: Iterable[str]) -> int:
    """Return the smaller one-sided player difference between two lineups."""
    left, right = set(a), set(b)
    return min(len(left - right), len(right - left))


def select_post_sim_portfolio(
    results_df: pd.DataFrame,
    lineup_count: int,
    metric: str = "Expected ROI (%)",
    min_uniques: int = 0,
    lineup_columns: Sequence[str] = SHOWDOWN_SLOTS,
) -> pd.DataFrame:
    """Select the best already-simulated lineups subject to user min-uniques.

    min_uniques=0 means no forced diversification. Higher values require every
    newly selected lineup to differ from every previously selected lineup by at
    least that many players. There is deliberately no hidden exposure ceiling or
    automatic uniqueness rule here.
    """
    if not isinstance(results_df, pd.DataFrame) or results_df.empty:
        raise ValueError("results_df must contain scored candidate lineups")
    if int(lineup_count) != lineup_count or lineup_count < 1:
        raise ValueError("lineup_count must be a positive integer")
    lineup_columns = tuple(lineup_columns)
    missing = [column for column in lineup_columns if column not in results_df.columns]
    if missing:
        raise KeyError("missing lineup columns: " + ", ".join(missing))
    if metric not in results_df.columns:
        raise KeyError(f"ranking metric not found: {metric}")
    if int(min_uniques) != min_uniques or min_uniques < 0 or min_uniques > len(lineup_columns):
        raise ValueError("min_uniques must be an integer between zero and roster size")

    ranked = results_df.drop_duplicates(subset=list(lineup_columns), keep="first").copy()
    ranked[metric] = pd.to_numeric(ranked[metric], errors="coerce")
    ranked = ranked[ranked[metric].notna()].sort_values(metric, ascending=False, kind="stable")

    selected_indices: list[int] = []
    selected_players: list[frozenset[str]] = []
    for index, row in ranked.iterrows():
        players = _lineup_players(row, lineup_columns)
        if min_uniques and any(min_unique_players(players, prior) < min_uniques for prior in selected_players):
            continue
        selected_indices.append(index)
        selected_players.append(players)
        if len(selected_indices) >= int(lineup_count):
            break

    portfolio = ranked.loc[selected_indices].copy().reset_index(drop=True)
    portfolio["Locked"] = False
    return portfolio
