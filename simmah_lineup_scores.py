"""Bounded, ordered sparse scoring for NFL candidate and contest matrices."""
import numpy as np
from scipy.sparse import csr_matrix


class LineupScorer:
    """Prepare slot weights once; preserve slot addition order and score precision."""
    def __init__(self, picks, multipliers, player_count, dtype=np.float64):
        picks = np.asarray(picks)
        weights = np.asarray(multipliers, dtype=dtype)
        if picks.ndim != 2 or not picks.shape[1] or picks.dtype.kind not in 'iu':
            raise ValueError('Two-dimensional integer lineup indices required')
        if (picks < 0).any() or (picks >= player_count).any():
            raise ValueError('Lineup indices must refer to outcome columns')
        if weights.shape != (picks.shape[1],) or not np.isfinite(weights).all():
            raise ValueError('Finite weights aligned with roster slots required')
        self.player_count = int(player_count)
        self.dtype = np.dtype(dtype)
        self.picks, self.weights = picks, weights
        self.unit_weights = bool(np.isin(weights, [0., 1., -1.]).all())
        self.captain_weights = bool(np.isin(weights, [0., 1., -1., 1.5, -1.5]).all())
        # Build CSR directly: sorting/coalescing repeated player indices would
        # change floating-point addition order and potentially break exact ties.
        self.matrix = csr_matrix((np.tile(weights, len(picks)), picks.ravel(),
            np.arange(0, picks.size + 1, picks.shape[1])),
            shape=(len(picks), self.player_count))

    def __call__(self, outcomes):
        values = np.asarray(outcomes)
        if values.ndim != 2 or values.shape[1] != self.player_count:
            raise ValueError('Outcome columns do not match prepared lineup scores')
        exact_weight_products = self.unit_weights or (self.captain_weights and values.dtype == np.dtype('float32') and self.dtype == np.dtype('float64'))
        if np.result_type(values.dtype, self.dtype) != self.dtype or not exact_weight_products:
            # Preserve per-slot promotion followed by accumulation rounding,
            # e.g. float64 inputs accumulated into float32 summary scores.
            # Separate multiply/add also avoids hardware-dependent fused rounding
            # when fractional slot weights do not have an exact product.
            major = np.ascontiguousarray(values.T)
            scores = np.zeros((len(self.picks), len(values)), dtype=self.dtype)
            for slot, weight in enumerate(self.weights):
                scores += major[self.picks[:, slot]] * weight
            return np.ascontiguousarray(scores.T)
        # Both axes become contiguous for the kernels that consume them.
        values = np.ascontiguousarray(values.T, dtype=self.dtype)
        return np.ascontiguousarray((self.matrix @ values).T)
