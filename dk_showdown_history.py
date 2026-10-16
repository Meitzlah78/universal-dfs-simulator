"""Historical-contest helpers for DK Showdown calibration."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, Mapping, Any

import numpy as np


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime): raise TypeError("lock_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None: raise ValueError("lock_time must be timezone-aware")
    return value.astimezone(timezone.utc)


def eligible_training_contests(contests: Iterable[Mapping[str, Any]], target_lock: datetime) -> list[Mapping[str, Any]]:
    target_utc = _utc(target_lock); eligible = []
    for contest in contests:
        if "lock_time" not in contest: raise KeyError("historical contest is missing lock_time")
        if _utc(contest["lock_time"]) < target_utc: eligible.append(contest)
    return eligible


def walk_forward_splits(contests: Iterable[Mapping[str, Any]], min_training_contests: int = 1) -> list[dict[str, Any]]:
    """Create strict chronological train/test splits, one held-out contest at a time."""
    if min_training_contests < 1: raise ValueError("min_training_contests must be positive")
    rows = list(contests)
    for contest in rows:
        if "lock_time" not in contest: raise KeyError("historical contest is missing lock_time")
        _utc(contest["lock_time"])
    ordered = sorted(rows, key=lambda c: _utc(c["lock_time"]))
    splits = []
    for target in ordered:
        training = eligible_training_contests(ordered, target["lock_time"])
        if len(training) >= min_training_contests:
            splits.append({"training": training, "target": target})
    return splits


def field_behavior_features(lineup_keys: Iterable[Any]) -> dict[str, float]:
    keys = list(lineup_keys)
    if not keys: raise ValueError("at least one lineup is required")
    counts = Counter(keys); entries = len(keys); unique = len(counts); duplicate_counts = list(counts.values())
    return {"entries": float(entries), "unique_lineups": float(unique), "unique_rate": unique / entries,
            "singleton_entry_mass": sum(c for c in duplicate_counts if c == 1) / entries,
            "ten_plus_duplicate_entry_mass": sum(c for c in duplicate_counts if c >= 10) / entries,
            "twenty_plus_duplicate_entry_mass": sum(c for c in duplicate_counts if c >= 20) / entries,
            "max_duplicates": float(max(duplicate_counts))}


def salary_behavior_features(salaries: Iterable[float]) -> dict[str, float]:
    values = np.asarray(list(salaries), dtype=float)
    if values.size == 0: raise ValueError("at least one salary is required")
    if not np.isfinite(values).all() or (values < 0).any(): raise ValueError("salaries must be finite and non-negative")
    q05, q10, q25, q50, q75, q90, q95 = np.percentile(values, [5, 10, 25, 50, 75, 90, 95])
    return {"salary_mean": float(values.mean()), "salary_p05": float(q05), "salary_p10": float(q10), "salary_p25": float(q25), "salary_median": float(q50), "salary_p75": float(q75), "salary_p90": float(q90), "salary_p95": float(q95)}


def captain_behavior_features(captains: Iterable[Any]) -> dict[str, float]:
    values = list(captains)
    if not values: raise ValueError("at least one captain is required")
    counts = Counter(values); entries = len(values); ordered = sorted(counts.values(), reverse=True)
    return {"captain_unique_count": float(len(counts)), "captain_top1_mass": ordered[0] / entries, "captain_top4_mass": sum(ordered[:4]) / entries}


def _validated_ev_arrays(predicted_roi, realized_net, entry_fees):
    pred = np.asarray(list(predicted_roi), dtype=float); net = np.asarray(list(realized_net), dtype=float); fees = np.asarray(list(entry_fees), dtype=float)
    if pred.size == 0 or pred.size != net.size or pred.size != fees.size: raise ValueError("predicted ROI, realized net, and entry fees must have equal non-zero length")
    if not (np.isfinite(pred).all() and np.isfinite(net).all() and np.isfinite(fees).all()): raise ValueError("EV calibration inputs must be finite")
    if (fees <= 0).any(): raise ValueError("entry fees must be positive")
    return pred, net, fees


def ev_calibration_features(predicted_roi, realized_net, entry_fees) -> dict[str, float]:
    pred, net, fees = _validated_ev_arrays(predicted_roi, realized_net, entry_fees); actual_roi = 100.0 * net / fees; positive = pred > 0; negative = ~positive
    result = {"lineups": float(pred.size), "predicted_positive_ev_rate": float(positive.mean()), "realized_roi": float(100.0 * net.sum() / fees.sum()), "roi_mae": float(np.mean(np.abs(pred - actual_roi)))}
    result["positive_ev_realized_roi"] = float(100.0 * net[positive].sum() / fees[positive].sum()) if positive.any() else float("nan")
    result["nonpositive_ev_realized_roi"] = float(100.0 * net[negative].sum() / fees[negative].sum()) if negative.any() else float("nan")
    return result


def ev_ranking_features(predicted_roi, realized_net, entry_fees, top_fraction: float = 0.20) -> dict[str, float]:
    pred, net, fees = _validated_ev_arrays(predicted_roi, realized_net, entry_fees)
    if not 0 < top_fraction < 1: raise ValueError("top_fraction must be between zero and one")
    n_top = max(1, int(np.ceil(pred.size * top_fraction))); order = np.argsort(-pred, kind="stable"); top = order[:n_top]; rest = order[n_top:]
    top_roi = 100.0 * net[top].sum() / fees[top].sum(); rest_roi = 100.0 * net[rest].sum() / fees[rest].sum() if rest.size else float("nan")
    return {"top_count": float(n_top), "top_predicted_ev_realized_roi": float(top_roi), "remaining_realized_roi": float(rest_roi), "top_ev_roi_lift": float(top_roi - rest_roi) if rest.size else float("nan")}
