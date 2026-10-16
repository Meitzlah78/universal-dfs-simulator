"""DraftKings Showdown engine primitives."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

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
    return str(captain), tuple(sorted(str(player) for player in flex))

def lineup_salary(captain_index: int, flex_indices: Sequence[int], salaries: np.ndarray, rules: ShowdownRules = ShowdownRules()) -> int:
    captain_salary = float(salaries[int(captain_index)]) * rules.captain_salary_multiplier
    flex_salary = float(np.sum(salaries[np.asarray(flex_indices, dtype=int)]))
    return int(round(captain_salary + flex_salary))

def candidate_score(captain: str, flex: Sequence[str], player_sim: Mapping[str, Mapping[str, float]], ownership_proxy: Mapping[str, float], p95_weight: float, p99_weight: float, mean_weight: float, stddev_weight: float, rules: ShowdownRules = ShowdownRules()) -> dict[str, float]:
    flex_players = tuple(str(player) for player in flex)
    if len(flex_players) != rules.flex_count:
        raise ValueError(f"flex must contain exactly {rules.flex_count} players")
    captain_stats = player_sim[str(captain)]
    total_mean = float(captain_stats["Mean"]) * rules.captain_points_multiplier + sum(float(player_sim[p]["Mean"]) for p in flex_players)
    total_p95 = float(captain_stats["P95"]) * rules.captain_points_multiplier + sum(float(player_sim[p]["P95"]) for p in flex_players)
    total_p99 = float(captain_stats["P99"]) * rules.captain_points_multiplier + sum(float(player_sim[p]["P99"]) for p in flex_players)
    total_stddev = float(captain_stats.get("StdDev", 0.0)) * rules.captain_points_multiplier + sum(float(player_sim[p].get("StdDev", 0.0)) for p in flex_players)
    raw_score = total_p95 * float(p95_weight) + total_p99 * float(p99_weight) + total_mean * float(mean_weight) + total_stddev * float(stddev_weight)
    lineup_ownership = float(ownership_proxy[str(captain)]) * rules.captain_points_multiplier + sum(float(ownership_proxy[p]) for p in flex_players)
    lineup_upside = max(0.0, total_p99 - total_p95)
    ownership_tax = max(0.0, lineup_ownership - 15.0 * 6.5) * 0.06
    upside_credit = min(ownership_tax, lineup_upside * 0.08)
    return {"SimMean": total_mean, "SimP95": total_p95, "SimP99": total_p99, "Score": raw_score - ownership_tax + upside_credit}

def duplicate_expansion_weights(log_weights: Sequence[float]) -> np.ndarray:
    values = np.asarray(log_weights, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("log_weights must be one-dimensional")
    total = len(values)
    if total == 0:
        return np.asarray([], dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("log_weights must be finite")
    centered = values - np.max(values)
    base = np.exp(centered * 0.38); base /= base.sum()
    broad_count = min(max(250, min(1800, max(250, total // 5))), total)
    broad_idx = np.argpartition(values, -broad_count)[-broad_count:]
    broad = np.zeros(total); strength = np.exp(centered[broad_idx] * 0.80)
    if strength.sum() > 0: broad[broad_idx] = strength / strength.sum()
    top_count = min(max(10, min(40, total)), total)
    top_idx = np.argpartition(values, -top_count)[-top_count:]
    top = np.zeros(total); strength = np.exp(centered[top_idx] * 1.20)
    if strength.sum() > 0: top[top_idx] = strength / strength.sum()
    weights = 0.76 * base + 0.20 * broad + 0.04 * top
    return weights / weights.sum()

def sample_opponent_batch(rng: np.random.Generator, captain_weights: np.ndarray, flex_weights: np.ndarray, batch_size: int, flex_count: int = DK_FLEX_COUNT) -> tuple[np.ndarray, np.ndarray]:
    """Fast weighted Captain + FLEX sampling for a whole opponent batch."""
    cpt = np.asarray(captain_weights, dtype=np.float64)
    flex = np.asarray(flex_weights, dtype=np.float64)
    cpt = cpt / cpt.sum(); flex = flex / flex.sum()
    captains = rng.choice(len(cpt), size=int(batch_size), p=cpt)
    scores = rng.gumbel(size=(int(batch_size), len(flex))) + np.log(flex)[None, :]
    scores[np.arange(int(batch_size)), captains] = -np.inf
    flex_indices = np.argpartition(scores, -int(flex_count), axis=1)[:, -int(flex_count):]
    return captains, flex_indices

def score_lineup_matrix(simulation_values: np.ndarray, captain_indices: np.ndarray, flex_indices: np.ndarray, rules: ShowdownRules = ShowdownRules()) -> np.ndarray:
    values = np.asarray(simulation_values, dtype=float)
    captains = np.asarray(captain_indices, dtype=int)
    flex = np.asarray(flex_indices, dtype=int)
    if flex.ndim != 2 or flex.shape[1] != rules.flex_count:
        raise ValueError(f"flex_indices must have shape (n, {rules.flex_count})")
    return values[:, captains] * rules.captain_points_multiplier + np.take(values, flex, axis=1).sum(axis=2)

def exact_duplicate_counts(lineups: pd.DataFrame) -> pd.Series:
    required = ["Captain"] + [f"Flex{i}" for i in range(1, DK_FLEX_COUNT + 1)]
    missing = [c for c in required if c not in lineups.columns]
    if missing:
        raise ValueError(f"Missing Showdown columns: {missing}")
    keys = [lineup_key(row["Captain"], [row[f"Flex{i}"] for i in range(1, DK_FLEX_COUNT + 1)]) for _, row in lineups[required].iterrows()]
    counts = pd.Series(keys).value_counts()
    return pd.Series([int(counts[key]) for key in keys], index=lineups.index, dtype=int)
