"""Post-contest-sim portfolio selection helpers.

Candidate generation and contest simulation happen before this module is used.
Diversification only selects from already-scored lineups; it never changes or
filters the 5,000-lineup candidate build.
"""

from __future__ import annotations

from math import ceil
from typing import Iterable, Mapping, Sequence

import pandas as pd


SHOWDOWN_SLOTS = ("Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5")


def _lineup_players(row: pd.Series, lineup_columns: Sequence[str]) -> frozenset[str]:
    return frozenset(str(row[column]) for column in lineup_columns)


def min_unique_players(a: Iterable[str], b: Iterable[str]) -> int:
    """Return the smaller one-sided player difference between two lineups."""
    left, right = set(a), set(b)
    return min(len(left - right), len(right - left))


def _exposure_limit(lineup_count: int, percent: float) -> int:
    percent = max(0.0, min(100.0, float(percent)))
    return int(ceil(lineup_count * percent / 100.0)) if percent > 0 else 0


def select_post_sim_portfolio(
    results_df: pd.DataFrame,
    lineup_count: int,
    metric: str = "Expected ROI (%)",
    min_uniques: int = 0,
    lineup_columns: Sequence[str] = SHOWDOWN_SLOTS,
    max_exposure: Mapping[str, float] | None = None,
    captain_max_exposure: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Select the best already-simulated lineups under explicit user constraints.

    ``min_uniques=0`` means no forced diversification. Higher values require every
    newly selected lineup to differ from every previously selected lineup by at
    least that many players. ``max_exposure`` and ``captain_max_exposure`` are
    explicit user limits expressed as percentages of the requested portfolio.

    There is deliberately no hidden exposure ceiling or automatic uniqueness rule.
    Candidate generation is unaffected by every option in this function.
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

    max_exposure = dict(max_exposure or {})
    captain_max_exposure = dict(captain_max_exposure or {})
    player_limits = {
        str(player): _exposure_limit(int(lineup_count), percent)
        for player, percent in max_exposure.items()
    }
    captain_limits = {
        str(player): _exposure_limit(int(lineup_count), percent)
        for player, percent in captain_max_exposure.items()
    }

    ranked = results_df.drop_duplicates(subset=list(lineup_columns), keep="first").copy()
    ranked[metric] = pd.to_numeric(ranked[metric], errors="coerce")
    ranked = ranked[ranked[metric].notna()].sort_values(metric, ascending=False, kind="stable")

    selected_indices: list[int] = []
    selected_players: list[frozenset[str]] = []
    player_counts: dict[str, int] = {}
    captain_counts: dict[str, int] = {}
    captain_column = lineup_columns[0] if lineup_columns else None

    for index, row in ranked.iterrows():
        players = _lineup_players(row, lineup_columns)
        if min_uniques and any(min_unique_players(players, prior) < min_uniques for prior in selected_players):
            continue
        if any(
            player_counts.get(player, 0) >= player_limits.get(player, int(lineup_count))
            for player in players
        ):
            continue
        captain = str(row[captain_column]) if captain_column else ""
        if captain_counts.get(captain, 0) >= captain_limits.get(captain, int(lineup_count)):
            continue

        selected_indices.append(index)
        selected_players.append(players)
        for player in players:
            player_counts[player] = player_counts.get(player, 0) + 1
        if captain_column:
            captain_counts[captain] = captain_counts.get(captain, 0) + 1
        if len(selected_indices) >= int(lineup_count):
            break

    portfolio = ranked.loc[selected_indices].copy().reset_index(drop=True)
    portfolio["Locked"] = False
    return portfolio
