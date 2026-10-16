from pathlib import Path

engine = Path('dk_showdown_engine.py')
text = engine.read_text()
old = '''    weights = 0.76 * base + 0.20 * broad + 0.04 * top
    return weights / weights.sum()
'''
new = '''    weights = 0.57 * base + 0.25 * broad + 0.18 * top
    return weights / weights.sum()


def duplicate_expansion_counts(log_weights: Sequence[float], full_field_size: int, seed: int = 20261012, singleton_share: float = 0.106) -> np.ndarray:
    """Allocate full-field multiplicities with a preserved low-owned tail.

    Real DK Showdown fields are polarized: many constructions appear once while
    a large share of entries sit in heavily duplicated chalk.  Redrawing every
    entry from a representative sample suppresses the singleton tail.  Preserve
    the least-popular representative constructions once, then allocate the
    remaining entries with the calibrated chalk distribution.
    """
    values = np.asarray(log_weights, dtype=np.float64)
    total = len(values)
    size = int(full_field_size)
    if total == 0 or size <= 0:
        return np.zeros(total, dtype=np.int64)
    if size <= total:
        counts = np.zeros(total, dtype=np.int64)
        counts[np.argsort(values)[:size]] = 1
        return counts
    weights = duplicate_expansion_weights(values)
    reserve = min(total, max(0, int(round(size * float(singleton_share)))))
    tail_idx = np.argsort(weights)[:reserve]
    counts = np.zeros(total, dtype=np.int64)
    counts[tail_idx] = 1
    remaining_mask = np.ones(total, dtype=bool)
    remaining_mask[tail_idx] = False
    remaining_weights = weights[remaining_mask]
    remaining_weights /= remaining_weights.sum()
    rng = np.random.default_rng(seed)
    counts[remaining_mask] = rng.multinomial(size - reserve, remaining_weights)
    return counts
'''
if old not in text:
    raise SystemExit('engine duplicate weight marker not found')
engine.write_text(text.replace(old, new, 1))

app = Path('dfs_app.py')
text = app.read_text()
old_import = '    duplicate_expansion_weights as dk_duplicate_expansion_weights,\n'
new_import = '    duplicate_expansion_counts as dk_duplicate_expansion_counts,\n    duplicate_expansion_weights as dk_duplicate_expansion_weights,\n'
if new_import not in text:
    if old_import not in text:
        raise SystemExit('app import marker not found')
    text = text.replace(old_import, new_import, 1)
old_draw = '''    weights = dk_duplicate_expansion_weights(log_weights)

    rng = np.random.default_rng(seed)
    sampled_indices = rng.choice(total, size=full_field_size, replace=True, p=weights)
    expanded = field.iloc[sampled_indices].copy().reset_index(drop=True)
'''
new_draw = '''    multiplicities = dk_duplicate_expansion_counts(log_weights, full_field_size, seed=seed)
    sampled_indices = np.repeat(np.arange(total, dtype=np.int64), multiplicities)
    expanded = field.iloc[sampled_indices].copy().reset_index(drop=True)
'''
if old_draw not in text:
    raise SystemExit('app duplicate draw marker not found')
app.write_text(text.replace(old_draw, new_draw, 1))
