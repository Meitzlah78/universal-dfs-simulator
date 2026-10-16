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

def opponent_lineup_means(captain_indices: Sequence[int], flex_indices: np.ndarray, player_means: Sequence[float], rules: ShowdownRules = ShowdownRules()) -> np.ndarray:
    """Projected mean for sampled opponent lineups.

    This is intentionally separate from ownership sampling. Public ownership says
    which players the field uses; lineup-quality acceptance models the fact that
    real entrants still tend to combine those players into reasonably strong
    constructions instead of accepting every legal ownership-weighted draw.
    """
    means = np.asarray(player_means, dtype=np.float64)
    captains = np.asarray(captain_indices, dtype=np.intp)
    flex = np.asarray(flex_indices, dtype=np.intp)
    if captains.ndim != 1:
        raise ValueError("captain_indices must be one-dimensional")
    if flex.ndim != 2 or flex.shape != (len(captains), rules.flex_count):
        raise ValueError(f"flex_indices must have shape (n, {rules.flex_count})")
    return means[captains] * rules.captain_points_multiplier + means[flex].sum(axis=1)

def opponent_quality_acceptance(lineup_means: Sequence[float], reference_mean: float | None = None) -> np.ndarray:
    """Softly reject weak ownership-weighted opponent constructions.

    The curve is deliberately modest: strong/publicly sensible lineups are kept,
    while the low-quality tail is thinned rather than removed.  That preserves
    contrarian field entries without letting independent player sampling create
    an unrealistically soft contest field.
    """
    values = np.asarray(lineup_means, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("lineup_means must be one-dimensional")
    if not len(values):
        return np.asarray([], dtype=np.float64)
    finite = values[np.isfinite(values)]
    if not len(finite):
        return np.zeros(len(values), dtype=np.float64)
    center = float(np.median(finite) if reference_mean is None else reference_mean)
    scale = max(float(np.std(finite)), 1.0)
    z = (values - center) / scale
    # Logistic transition with a non-zero floor keeps a realistic bad-lineup tail.
    acceptance = 0.18 + 0.82 / (1.0 + np.exp(-1.35 * (z + 0.35)))
    return np.clip(acceptance, 0.18, 1.0)

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
    weights = 0.57 * base + 0.25 * broad + 0.18 * top
    return weights / weights.sum()


def duplicate_expansion_counts(log_weights: Sequence[float], full_field_size: int, seed: int = 20261012, singleton_share: float = 0.106) -> np.ndarray:
    """Allocate full-field multiplicities with a preserved low-owned tail.

    Real DK Showdown fields are polarized: many constructions appear once while
    a large share of entries sit in heavily duplicated chalk.  Redrawing every
    entry from a representative sample suppresses the singleton tail.  Preserve
    the least-popular representative constructions once, then allocate the
    remaining entries with the calibrated chalk distribution.
    """
    values = np.asarray(log_weights, dtype=np.float64)
    total = len(values)
    size = int(full_field_size)
    if total == 0 or size <= 0:
        return np.zeros(total, dtype=np.int64)
    if size <= total:
        counts = np.zeros(total, dtype=np.int64)
        counts[np.argsort(values)[:size]] = 1
        return counts
    weights = duplicate_expansion_weights(values)
    reserve = min(total, max(0, int(round(size * float(singleton_share)))))
    tail_idx = np.argsort(weights)[:reserve]
    counts = np.zeros(total, dtype=np.int64)
    counts[tail_idx] = 1
    remaining_mask = np.ones(total, dtype=bool)
    remaining_mask[tail_idx] = False
    remaining_weights = weights[remaining_mask]
    remaining_weights /= remaining_weights.sum()
    rng = np.random.default_rng(seed)
    counts[remaining_mask] = rng.multinomial(size - reserve, remaining_weights)
    return counts

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
    """Score all Showdown lineups for a simulation block without Python lineup loops."""
    values = np.asarray(simulation_values)
    captains = np.asarray(captain_indices, dtype=np.intp)
    flex = np.asarray(flex_indices, dtype=np.intp)
    if values.ndim != 2:
        raise ValueError("simulation_values must have shape (simulations, players)")
    if captains.ndim != 1:
        raise ValueError("captain_indices must be one-dimensional")
    if flex.ndim != 2 or flex.shape != (len(captains), rules.flex_count):
        raise ValueError(f"flex_indices must have shape (n, {rules.flex_count})")
    captain_scores = values[:, captains] * rules.captain_points_multiplier
    flex_scores = values[:, flex].sum(axis=2)
    return captain_scores + flex_scores

def weighted_score_bounds(unique_scores: np.ndarray, multiplicities: np.ndarray, candidate_scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return expanded-field left/right positions without expanding duplicates.

    The unique field is sorted once per simulation. Native NumPy searchsorted then
    locates every candidate in that row, while cumulative multiplicities convert
    unique-lineup positions back to exact full-field entry counts.
    """
    scores = np.asarray(unique_scores)
    counts = np.asarray(multiplicities, dtype=np.int64)
    candidates = np.asarray(candidate_scores)
    if scores.ndim != 2:
        raise ValueError("unique_scores must have shape (simulations, unique_lineups)")
    if counts.ndim != 1 or counts.shape[0] != scores.shape[1]:
        raise ValueError("multiplicities must match unique_scores columns")
    if candidates.ndim != 2 or candidates.shape[0] != scores.shape[0]:
        raise ValueError("candidate_scores must have the same simulation rows")
    if np.any(counts < 1):
        raise ValueError("multiplicities must be positive")

    order = np.argsort(scores, axis=1, kind="stable")
    sorted_scores = np.take_along_axis(scores, order, axis=1)
    cumulative = np.cumsum(counts[order], axis=1, dtype=np.int64)
    left = np.empty(candidates.shape, dtype=np.int64)
    right = np.empty(candidates.shape, dtype=np.int64)

    for row in range(scores.shape[0]):
        left_idx = np.searchsorted(sorted_scores[row], candidates[row], side="left")
        right_idx = np.searchsorted(sorted_scores[row], candidates[row], side="right")
        left[row] = np.where(left_idx > 0, cumulative[row, np.maximum(left_idx - 1, 0)], 0)
        right[row] = np.where(right_idx > 0, cumulative[row, np.maximum(right_idx - 1, 0)], 0)
    return left, right

def score_showdown_chunks(simulation_values: np.ndarray, lineup_indices: np.ndarray, chunk_size: int = 128, rules: ShowdownRules = ShowdownRules()):
    values = np.asarray(simulation_values)
    lineups = np.asarray(lineup_indices)
    if values.ndim != 2:
        raise ValueError("simulation_values must have shape (simulations, players)")
    if lineups.ndim != 2 or lineups.shape[1] != rules.flex_count + 1:
        raise ValueError(f"lineup_indices must have shape (n, {rules.flex_count + 1})")
    if int(chunk_size) < 1:
        raise ValueError("chunk_size must be at least 1")
    captains = lineups[:, 0].astype(np.intp, copy=False)
    flex = lineups[:, 1:].astype(np.intp, copy=False)
    for start in range(0, len(values), int(chunk_size)):
        end = min(start + int(chunk_size), len(values))
        yield start, end, score_lineup_matrix(values[start:end], captains, flex, rules)

def exact_duplicate_counts(lineups: pd.DataFrame) -> pd.Series:
    required = ["Captain"] + [f"Flex{i}" for i in range(1, DK_FLEX_COUNT + 1)]
    missing = [c for c in required if c not in lineups.columns]
    if missing:
        raise ValueError(f"Missing Showdown columns: {missing}")
    keys = [lineup_key(row["Captain"], [row[f"Flex{i}"] for i in range(1, DK_FLEX_COUNT + 1)]) for _, row in lineups[required].iterrows()]
    counts = pd.Series(keys).value_counts()
    return pd.Series([int(counts[key]) for key in keys], index=lineups.index, dtype=int)