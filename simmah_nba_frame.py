"""Read player values without propagating evidence into temporary pandas objects."""
import pandas as pd


def data_view(pool):
    """Read-only, dtype-preserving view; the original retains all metadata.

    Constructing from the existing frame reuses its columns but deliberately
    omits attrs. Never assign through this view: callers write to their own
    result frame. Row iteration otherwise deep-copies provider evidence for
    every Series, even when the caller only needs a handful of scalar values.
    """
    return pd.DataFrame(pool, copy=False)
