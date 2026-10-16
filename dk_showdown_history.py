"""Historical-contest helpers for DK Showdown calibration."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, Mapping, Any

import numpy as np


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("lock_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("lock_time must be timezone-aware")
    return value.astimezone(timezone.utc)


def eligible_training_contests(
    contests: Iterable[Mapping[str, Any]], target_lock: datetime
) -> list[Mapping[str, Any]]:
    """Return only contests whose lock occurred strictly before target_lock."""
    target_utc = _utc(target_lock)
    eligible: list[Mapping[str, Any]] = []
    for contest in contests:
        if "lock_time" not in contest:
            raise KeyError("historical contest is missing lock_time")
        if _utc(contest["lock_time"]) < target_utc:
            eligible.append(contest)
    return eligible


def field_behavior_features(lineup_keys: Iterable[Any]) -> dict[str, float]:
    """Summarize construction/duplication behavior without contest outcomes."""
    keys = list(lineup_keys)
    if not keys:
        raise ValueError("at least one lineup is required")
    counts = Counter(keys)
    entries = len(keys)
    unique = len(counts)
    duplicate_counts = list(counts.values())
    return {
        "entries": float(entries),
        "unique_lineups": float(unique),
        "unique_rate": unique / entries,
        "singleton_entry_mass": sum(c for c in duplicate_counts if c == 1) / entries,
        "ten_plus_duplicate_entry_mass": sum(c for c in duplicate_counts if c >= 10) / entries,
        "twenty_plus_duplicate_entry_mass": sum(c for c in duplicate_counts if c >= 20) / entries,
        "max_duplicates": float(max(duplicate_counts)),
    }


def salary_behavior_features(salaries: Iterable[float]) -> dict[str, float]:
    """Describe historical salary usage without looking at lineup results."""
    values = np.asarray(list(salaries), dtype=float)
    if values.size == 0:
        raise ValueError("at least one salary is required")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("salaries must be finite and non-negative")
    q05, q10, q25, q50, q75, q90, q95 = np.percentile(values, [5, 10, 25, 50, 75, 90, 95])
    return {
        "salary_mean": float(values.mean()),
        "salary_p05": float(q05),
        "salary_p10": float(q10),
        "salary_p25": float(q25),
        "salary_median": float(q50),
        "salary_p75": float(q75),
        "salary_p90": float(q90),
        "salary_p95": float(q95),
    }


def captain_behavior_features(captains: Iterable[Any]) -> dict[str, float]:
    """Describe field captain concentration without using fantasy outcomes."""
    values = list(captains)
    if not values:
        raise ValueError("at least one captain is required")
    counts = Counter(values)
    entries = len(values)
    ordered = sorted(counts.values(), reverse=True)
    return {
        "captain_unique_count": float(len(counts)),
        "captain_top1_mass": ordered[0] / entries,
        "captain_top4_mass": sum(ordered[:4]) / entries,
    }
