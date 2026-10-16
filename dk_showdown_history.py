"""Historical-contest helpers for DK Showdown calibration.

Completed contests may inform a future field model only when their lock time is
strictly earlier than the target slate.  Keep this rule in one production helper
so backtests and future learning code cannot silently use same-slate/future data.
"""

from __future__ import annotations

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
    """Return only contests whose lock occurred strictly before target_lock.

    Same-lock contests are excluded because their completed results were not
    available when the target slate locked.  Returned order follows input order.
    """
    target_utc = _utc(target_lock)
    eligible: list[Mapping[str, Any]] = []
    for contest in contests:
        if "lock_time" not in contest:
            raise KeyError("historical contest is missing lock_time")
        if _utc(contest["lock_time"]) < target_utc:
            eligible.append(contest)
    return eligible
