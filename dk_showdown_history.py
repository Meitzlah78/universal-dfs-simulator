"""Historical-contest helpers for DK Showdown calibration.

Completed contests may inform a future field model only when their lock time is
strictly earlier than the target slate. Keep this rule in one production helper
so backtests and future learning code cannot silently use same-slate/future data.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, Mapping, Any


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
    """Summarize construction/duplication behavior without using contest results.

    lineup_keys should identify complete roster constructions (including CPT).
    The returned features describe how entrants built lineups; scores, ranks,
    prizes, and winning status are intentionally not accepted by this helper.
    """
    keys = list(lineup_keys)
    if not keys:
        raise ValueError("at least one lineup is required")

    counts = Counter(keys)
    entries = len(keys)
    unique = len(counts)
    duplicate_counts = list(counts.values())

    singleton_entries = sum(count for count in duplicate_counts if count == 1)
    ten_plus_entries = sum(count for count in duplicate_counts if count >= 10)
    twenty_plus_entries = sum(count for count in duplicate_counts if count >= 20)

    return {
        "entries": float(entries),
        "unique_lineups": float(unique),
        "unique_rate": unique / entries,
        "singleton_entry_mass": singleton_entries / entries,
        "ten_plus_duplicate_entry_mass": ten_plus_entries / entries,
        "twenty_plus_duplicate_entry_mass": twenty_plus_entries / entries,
        "max_duplicates": float(max(duplicate_counts)),
    }
