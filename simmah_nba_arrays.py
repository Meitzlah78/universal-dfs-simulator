"""NumPy numerical boundary for NBA lineup scoring, independent of Streamlit."""
import numpy as np


def score_batches(player_outcomes, lineup_indices, batch_size=128):
    """Yield (simulation_start, lineup-by-simulation scores) in bounded batches.

    outcomes: simulations x players; indices: lineups x roster slots.
    All lineups share the same simulated player outcomes. Slot-wise gathers avoid
    a simulations x lineups x slots temporary and a large dense incidence matrix.
    A fixed loop over the nine roster slots performs vectorized NumPy operations;
    there is no Python loop over individual lineups or individual simulations.
    """
    outcomes=np.asarray(player_outcomes)
    indices=np.asarray(lineup_indices)
    if outcomes.ndim!=2 or indices.ndim!=2 or not indices.shape[1]:
        raise ValueError('Two-dimensional outcomes and nonempty roster slots required')
    if outcomes.dtype.kind not in 'fi' or not np.isfinite(outcomes).all():
        raise ValueError('Finite numeric player outcomes required')
    if indices.dtype.kind not in 'iu' or (indices<0).any() or (indices>=outcomes.shape[1]).any():
        raise ValueError('Lineup indices must refer to valid player columns')
    if batch_size<1 or int(batch_size)!=batch_size:
        raise ValueError('Positive integer batch size required')
    batch_size=int(batch_size)
    dtype=np.result_type(outcomes.dtype,np.float32)
    for start in range(0,len(outcomes),batch_size):
        values=outcomes[start:start+batch_size]
        scores=np.zeros((len(indices),len(values)),dtype=dtype)
        for slot in range(indices.shape[1]):
            scores+=values[:,indices[:,slot]].T
        yield start,scores
