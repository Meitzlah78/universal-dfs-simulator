"""Offline joint opponent-weight experiment; never imported by the live builder.

Callers supply unique, already legal support and frozen feature targets. Duplication
bands are entry-weighted count frequencies at the exact same opponent field size.
This is an IID lineup-distribution model, not a model of entrants' portfolios.
"""
from dataclasses import dataclass
import numpy as np
from scipy import sparse
from scipy.optimize import minimize
from scipy.special import logsumexp
from scipy.stats import binom

# Inclusive counts. The final band includes every count above its lower bound.
DUPLICATE_BANDS = ((1, 1), (2, 4), (5, 9), (10, 24), (25, 99), (100, None))


class JointFitNotConverged(ValueError):
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('Joint ownership/combination/duplication tolerances not met')


def _field_size(entries):
    if type(entries) is not int or not 1 <= entries <= 10_000_000:
        raise ValueError('Exact positive opponent field size required')
    return entries


def single_game_features(picks, n_players, pairs=()):
    """Sparse feature x lineup indicators: special, FLEX, then overall pairs.

    Support is canonicalized for duplicate detection only. FLEX permutations may
    not masquerade as different support rows. Legality is the caller's contract.
    """
    ids = np.asarray(picks)
    if (type(n_players) is not int or n_players < 6 or ids.ndim != 2
            or ids.shape[1] != 6 or not len(ids) or ids.dtype.kind not in 'iu'):
        raise ValueError('Integer J x 6 single-game support and player count required')
    if (ids < 0).any() or (ids >= n_players).any() or (np.diff(np.sort(ids, axis=1), axis=1) == 0).any():
        raise ValueError('Each roster needs six distinct in-range players')
    canonical = np.column_stack([ids[:, 0], np.sort(ids[:, 1:], axis=1)])
    if len(np.unique(canonical, axis=0)) != len(ids):
        raise ValueError('Support contains canonical duplicate rosters')
    pairs = tuple(pairs)
    if any(len(pair) != 2 or any(type(p) is not int or not 0 <= p < n_players for p in pair)
           or pair[0] >= pair[1] for pair in pairs) or len(set(pairs)) != len(pairs):
        raise ValueError('Unique ordered player-index pairs required')
    columns = np.arange(len(ids))
    rows = [ids[:, 0], *(n_players + ids[:, slot] for slot in range(1, 6))]
    cols = [columns] * 6
    for i, (a, b) in enumerate(pairs):
        present = np.flatnonzero((ids == a).any(axis=1) & (ids == b).any(axis=1))
        rows.append(np.full(len(present), 2*n_players+i))
        cols.append(present)
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    return sparse.coo_matrix((np.ones(len(rows)), (rows, cols)),
        shape=(2*n_players+len(pairs), len(ids))).tocsr()


def observed_duplicate_curve(counts, entries):
    """Entry fractions, not fractions of unique lineups; zeros allowed in support."""
    _field_size(entries)
    counts = np.asarray(counts)
    if (counts.ndim != 1 or counts.dtype.kind not in 'iu' or (counts < 0).any()
            or sum(map(int, counts)) != entries):
        raise ValueError('Integer lineup counts must sum to the exact field size')
    return np.array([counts[(counts >= low) & (counts <= (entries if high is None else high))].sum()/entries
                     for low, high in DUPLICATE_BANDS], dtype=float)


def expected_duplicate_curve(weights, entries, *, gradient=False):
    """Expected entry fractions under multinomial(N, weights), with exact gradient.

    A tagged entry's other copies follow Binomial(N-1, p), so its bin mass is
    p * P(low-1 <= copies <= high-1). No field is sampled inside optimization.
    """
    _field_size(entries)
    w = np.asarray(weights, dtype=float)
    if (w.ndim != 1 or not len(w) or not np.isfinite(w).all() or (w < 0).any()
            or (w > 1).any() or abs(w.sum()-1) > 1e-9):
        raise ValueError('Normalized finite nonnegative lineup probabilities required')
    values, derivatives = [], []
    n = entries-1
    for low, high in DUPLICATE_BANDS:
        upper = entries if high is None else high
        lo, hi = low-2, upper-1
        mass = binom.cdf(hi, n, w)-binom.cdf(lo, n, w)
        values.append(float(w @ mass))
        if gradient:
            slope = np.zeros_like(w) if n == 0 else n*(binom.pmf(lo, n-1, w)-binom.pmf(hi, n-1, w))
            derivatives.append(mass+w*slope)
    result = np.asarray(values)
    return (result, np.asarray(derivatives)) if gradient else result


@dataclass
class JointFieldFit:
    weights: np.ndarray
    counts: np.ndarray
    diagnostics: dict


def fit_joint_field(features, targets, prior, entries, duplicate_targets, *,
                    feature_tolerance, duplicate_tolerance, max_iterations=500,
                    kl_strength=1e-3, seed=83):
    """Fit all supplied targets simultaneously or raise; no live-model mutation.

    Tolerances are probabilities, not percentage points. Feature rows must be
    named/partitioned by the caller (role ownership, pairs, construction, etc.).
    Counts are one seeded multinomial realization, with its noise reported rather
    than rerolled until favorable. Actual targets are development-only after lock.
    """
    _field_size(entries)
    x = sparse.csr_matrix(features, dtype=float)
    y, q, duplicate = (np.asarray(v, dtype=float) for v in (targets, prior, duplicate_targets))
    if (not x.shape[0] or not x.shape[1] or y.shape != (x.shape[0],)
            or q.shape != (x.shape[1],) or duplicate.shape != (len(DUPLICATE_BANDS),)):
        raise ValueError('Aligned features, targets, prior, and duplication bands required')
    tol = np.broadcast_to(np.asarray(feature_tolerance, dtype=float), y.shape)
    if (not all(np.isfinite(v).all() for v in (x.data, y, q, duplicate, tol))
            or (x.data < 0).any() or (x.data > 1).any() or (y < 0).any() or (y > 1).any()
            or (q <= 0).any() or (duplicate < 0).any() or abs(duplicate.sum()-1) > 1e-9
            or (tol <= 0).any() or not np.isfinite(duplicate_tolerance) or duplicate_tolerance <= 0
            or type(max_iterations) is not int or max_iterations < 1
            or not np.isfinite(kl_strength) or kl_strength < 0):
        raise ValueError('Finite probabilities, positive prior/tolerances and valid solver controls required')
    q = q/q.sum()
    if not np.isfinite(q).all() or (q <= 0).any():
        raise ValueError('Prior normalization lost positive finite mass')
    low, high = x.min(axis=1).toarray().ravel(), x.max(axis=1).toarray().ravel()
    if ((y < low-tol) | (y > high+tol)).any():
        raise ValueError('Feature target is outside supplied support coverage')
    logq = np.log(q)

    def objective(theta):
        logits = logq+theta
        w = np.exp(logits-logsumexp(logits))
        achieved = np.asarray(x @ w).ravel()
        curve, derivative = expected_duplicate_curve(w, entries, gradient=True)
        feature_residual = (achieved-y)/tol
        duplicate_residual = (curve-duplicate)/duplicate_tolerance
        log_ratio = logits-logsumexp(logits)-logq
        loss = (feature_residual @ feature_residual)/(2*len(y))
        loss += (duplicate_residual @ duplicate_residual)/(2*len(duplicate))
        loss += kl_strength*float(w @ log_ratio)
        grad_w = np.asarray(x.T @ (feature_residual/tol/len(y))).ravel()
        grad_w += derivative.T @ (duplicate_residual/duplicate_tolerance/len(duplicate))
        grad_w += kl_strength*(log_ratio+1)
        return float(loss), w*(grad_w-float(w @ grad_w))

    solved = minimize(objective, np.zeros(len(q)), jac=True, method='L-BFGS-B',
        options={'maxiter':max_iterations, 'ftol':1e-13, 'gtol':1e-8, 'maxls':40})
    logits = logq+solved.x
    weights = np.exp(logits-logsumexp(logits))
    achieved = np.asarray(x @ weights).ravel()
    curve = expected_duplicate_curve(weights, entries)
    feature_errors, duplicate_errors = abs(achieved-y), abs(curve-duplicate)
    accepted = bool((feature_errors <= tol).all() and (duplicate_errors <= duplicate_tolerance).all())
    diagnostics = dict(accepted=accepted, offline_only=True, field_size=entries,
        support_size=len(q), optimizer_success=bool(solved.success), optimizer_message=str(solved.message),
        iterations=int(solved.nit), max_feature_error=float(feature_errors.max()),
        max_duplicate_band_error=float(duplicate_errors.max()),
        expected_features=achieved.tolist(), expected_duplicate_curve=curve.tolist(),
        target_duplicate_curve=duplicate.tolist(), seed=seed,
        assumption='IID multinomial lineup distribution; no entrant portfolio model')
    if not accepted:
        raise JointFitNotConverged(diagnostics)
    counts = np.random.default_rng(seed).multinomial(entries, weights)
    diagnostics.update(sampled_features=np.asarray(x @ (counts/entries)).ravel().tolist(),
        sampled_duplicate_curve=observed_duplicate_curve(counts, entries).tolist(),
        sampled_unique=int(np.count_nonzero(counts)), sampled_max_copies=int(counts.max()))
    return JointFieldFit(weights, counts, diagnostics)
