"""Bounded sparse numerical boundary for NBA lineup scoring, independent of UI."""
import numpy as np
from scipy.sparse import csr_matrix


def score_batches(player_outcomes, lineup_indices, batch_size=128):
    """Yield (simulation_start, lineup-by-simulation scores) in bounded batches.

    outcomes: simulations x players; indices: lineups x roster slots.
    All lineups share the same simulated player outcomes. A sparse lineup matrix
    stores roster slots in their original order and adds them in compiled code.
    No simulations x lineups x slots temporary or dense incidence matrix is used.
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
    # Construct directly from CSR buffers so SciPy retains the supplied slot
    # order, including repeated indices. Sorting or coalescing indices would
    # change floating-point addition order and could alter score-tick ties.
    incidence=None
    if dtype in (np.dtype('float32'),np.dtype('float64')):
        incidence=csr_matrix((np.ones(indices.size,dtype=dtype),indices.ravel(),
            np.arange(0,indices.size+1,indices.shape[1])),shape=(len(indices),outcomes.shape[1]))
    for start in range(0,len(outcomes),batch_size):
        # Copy only this bounded batch into player-major order once. Each
        # slot gather then reads contiguous simulation rows instead of
        # repeatedly gathering strided player columns and transposing them.
        values=np.ascontiguousarray(outcomes[start:start+batch_size].T)
        if incidence is None:
            # Preserve the existing NumPy boundary for extended precision
            # dtypes unsupported by SciPy's sparse multiplication kernels.
            scores=np.zeros((len(indices),values.shape[1]),dtype=dtype)
            for slot in range(indices.shape[1]):scores+=values[indices[:,slot]]
        else:scores=incidence@values
        yield start,scores

