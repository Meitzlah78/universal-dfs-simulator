"""Historical-field calibration used by the deployed DK Showdown opponent model."""
from __future__ import annotations

import numpy as np

from dk_showdown_engine import duplicate_expansion_weights


def calibrated_duplicate_expansion_counts(
    log_weights,
    full_field_size: int,
    seed: int = 20261012,
    singleton_share: float = 0.112,
    max_duplicate_share: float = 0.014,
):
    """Expand a representative field without collapsing it into a few lineups.

    Completed large-field DK Showdown uploads are stable enough to supply broad
    construction targets: roughly 20-23% unique lineups, about 10-12% singleton
    entry mass, and a chalk tail measured in hundreds rather than thousands.

    The old multinomial allocator could give one representative lineup thousands
    of copies when slate ownership was concentrated.  Preserve the representative
    field once, protect the learned singleton tail, then allocate the remaining
    entries by popularity subject to the historical maximum-duplicate envelope.
    """
    values = np.asarray(log_weights, dtype=np.float64)
    total = len(values)
    size = int(full_field_size)
    if total == 0 or size <= 0:
        return np.zeros(total, dtype=np.int64)
    if not np.all(np.isfinite(values)):
        raise ValueError("log_weights must be finite")
    if size <= total:
        counts = np.zeros(total, dtype=np.int64)
        counts[np.argsort(values)[:size]] = 1
        return counts

    weights = duplicate_expansion_weights(values)
    counts = np.ones(total, dtype=np.int64)

    # Historical uploads put about 10-12% of all entries in lineups appearing
    # exactly once. Keep the least-popular constructions protected at one copy.
    singleton_target = min(total - 1, max(0, int(round(size * float(singleton_share)))))
    protected = np.zeros(total, dtype=bool)
    if singleton_target:
        protected[np.argsort(weights)[:singleton_target]] = True

    eligible = ~protected
    cap = max(2, int(round(size * float(max_duplicate_share))))
    remaining = size - total
    rng = np.random.default_rng(seed)

    # Allocate in bounded rounds. The tiny seeded jitter only resolves exact
    # fractional ties; it does not alter the learned popularity ordering.
    while remaining > 0:
        room = np.maximum(cap - counts, 0)
        active = eligible & (room > 0)
        if not np.any(active):
            # Safety valve for unusually small fields/profiles: expand the cap
            # gradually rather than dropping entries.
            cap += max(1, int(round(size * 0.001)))
            continue
        active_idx = np.flatnonzero(active)
        active_weights = weights[active_idx]
        active_weights = active_weights / active_weights.sum()
        expected = active_weights * remaining
        add = np.minimum(np.floor(expected).astype(np.int64), room[active_idx])
        used = int(add.sum())
        if used:
            counts[active_idx] += add
            remaining -= used
            if remaining <= 0:
                break
        room = np.maximum(cap - counts, 0)
        active = eligible & (room > 0)
        active_idx = np.flatnonzero(active)
        if not len(active_idx):
            continue
        fractions = (weights[active_idx] / weights[active_idx].sum()) * remaining
        jitter = rng.random(len(active_idx)) * 1e-12
        order = active_idx[np.argsort(-(fractions + jitter))]
        take = min(remaining, len(order))
        counts[order[:take]] += 1
        remaining -= take

    return counts
