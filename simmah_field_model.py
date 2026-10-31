"""Shared contest-field learning primitives for Simmah.

This module keeps field-learning platform agnostic.  Platform/mode adapters turn
real contest lineups into normalized feature rows; the learned distributions can
then be consumed by each opponent-lineup generator.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ContestContext:
    platform: str
    mode: str
    sport: str = "NFL"
    field_size: int = 0
    max_entries: int = 0
    entry_fee: float = 0.0
    contest_type: str = "GPP"

    def normalized(self) -> dict:
        out = asdict(self)
        out["platform"] = str(out["platform"]).strip().upper()
        out["mode"] = str(out["mode"]).strip().upper()
        out["sport"] = str(out["sport"]).strip().upper()
        out["contest_type"] = str(out["contest_type"]).strip().upper()
        return out


NORMALIZED_FEATURES = (
    "salary_used",
    "salary_left",
    "projection",
    "ownership_sum",
    "ownership_product_log",
    "duplicate_count",
    "qb_stack_count",
    "qb_pass_catcher_stack_count",
    "bring_back_count",
    "rb_dst_stack",
    "flex_rb",
    "flex_wr",
    "flex_te",
    "captain_ownership",
    "mvp_ownership",
)


def _num(value, default=np.nan) -> float:
    try:
        x = float(value)
        return x if np.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def normalize_feature_rows(rows: Iterable[Mapping], context: ContestContext) -> pd.DataFrame:
    """Normalize adapter output into one cross-platform training table."""
    ctx = context.normalized()
    records = []
    for row in rows:
        rec = dict(ctx)
        for feature in NORMALIZED_FEATURES:
            rec[feature] = _num(row.get(feature))
        records.append(rec)
    return pd.DataFrame.from_records(records)


def learn_field_profile(feature_rows: pd.DataFrame) -> dict:
    """Learn robust empirical distributions from real contest lineups.

    Returns quantiles/rates rather than a fitted black-box model so the field
    generator remains inspectable and deterministic enough to calibrate.
    """
    if feature_rows is None or feature_rows.empty:
        return {"lineups": 0, "features": {}}

    learned = {"lineups": int(len(feature_rows)), "features": {}}
    for col in NORMALIZED_FEATURES:
        if col not in feature_rows:
            continue
        values = pd.to_numeric(feature_rows[col], errors="coerce").dropna().to_numpy(float)
        if not len(values):
            continue
        learned["features"][col] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "q05": float(np.quantile(values, 0.05)),
            "q25": float(np.quantile(values, 0.25)),
            "q50": float(np.quantile(values, 0.50)),
            "q75": float(np.quantile(values, 0.75)),
            "q95": float(np.quantile(values, 0.95)),
        }
    return learned


def profile_distance(candidate_features: Mapping[str, np.ndarray], profile: Mapping) -> np.ndarray:
    """Vectorized distance from candidate lineups to an observed field profile.

    Lower values are more human-field-like.  Missing features are ignored.
    """
    n = 0
    for values in candidate_features.values():
        n = len(values)
        break
    distance = np.zeros(n, dtype=np.float64)
    used = np.zeros(n, dtype=np.float64)
    learned = profile.get("features", {}) if profile else {}
    for name, values in candidate_features.items():
        stats = learned.get(name)
        if not stats:
            continue
        arr = np.asarray(values, dtype=np.float64)
        scale = max(float(stats.get("std", 0.0)), 1.0)
        z = np.clip((arr - float(stats["mean"])) / scale, -5.0, 5.0)
        good = np.isfinite(z)
        distance[good] += z[good] * z[good]
        used[good] += 1.0
    return np.divide(distance, np.maximum(used, 1.0))


def field_likeness_weights(candidate_features: Mapping[str, np.ndarray], profile: Mapping, temperature: float = 1.0) -> np.ndarray:
    """Return normalized NumPy sampling weights matching learned field behavior."""
    d = profile_distance(candidate_features, profile)
    t = max(float(temperature), 0.05)
    w = np.exp(-0.5 * d / t)
    w = np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0)
    total = float(w.sum())
    if total <= 0:
        return np.full(len(w), 1.0 / max(len(w), 1), dtype=np.float64)
    return w / total


def select_profile(history: pd.DataFrame, context: ContestContext) -> pd.DataFrame:
    """Select the most relevant historical contests, backing off gracefully.

    Priority: exact sport/platform/mode, then sport/platform, then sport. This
    lets all platforms share one history store without pretending roster formats
    are interchangeable.
    """
    if history is None or history.empty:
        return pd.DataFrame()
    ctx = context.normalized()
    h = history.copy()
    for col in ("sport", "platform", "mode"):
        if col in h:
            h[col] = h[col].astype(str).str.upper()
    masks = [
        (h.get("sport") == ctx["sport"]) & (h.get("platform") == ctx["platform"]) & (h.get("mode") == ctx["mode"]),
        (h.get("sport") == ctx["sport"]) & (h.get("platform") == ctx["platform"]),
        (h.get("sport") == ctx["sport"]),
    ]
    for mask in masks:
        subset = h.loc[mask]
        if len(subset):
            return subset
    return pd.DataFrame()
