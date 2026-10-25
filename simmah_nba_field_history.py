"""Anonymous, dated NBA contest habits; never learn from points or winning ranks.

Profiles describe salary left and team/game concentration, not future player
ownership. A bounded density-ratio prior reweights the current legal support.
It cannot add missing rosters or establish out-of-sample improvement.
"""
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from simmah_nba_rules import rules_for

PROFILE_DIR = Path(__file__).parent / 'data' / 'nba_field_history'
FEATURES = ('salary_left', 'max_team', 'max_game')


def fee_bucket(fee):
    if not np.isfinite(fee) or fee < 0:
        raise ValueError('Nonnegative contest fee required')
    return 'micro' if fee <= 1 else 'low' if fee <= 10 else 'higher'


def game_bucket(games):
    return 'small' if games <= 3 else 'medium' if games <= 7 else 'large'


def game_count(pool):
    return len({tuple(sorted((str(r.Team), str(r.Opponent)))) for r in pool.itertuples()})


def lineup_features(pool, lineups):
    """Aligned feature bins. Salary bins are fractions of cap, not player IDs."""
    ids = np.asarray(lineups)
    rules = rules_for(pool)
    if (ids.ndim != 2 or ids.shape[1] != len(rules['slots']) or
            ids.dtype.kind not in 'iu' or not len(ids) or
            (ids < 0).any() or (ids >= len(pool)).any() or
            (np.diff(np.sort(ids, axis=1), axis=1) == 0).any()):
        raise ValueError('Valid original-pool roster indices required')
    salaries = np.asarray(pool['Salary'], dtype=float)
    if not np.isfinite(salaries).all() or (salaries <= 0).any() or (salaries != np.floor(salaries)).any():
        raise ValueError('Positive integer historical salaries required')
    left = rules['salary_cap'] - salaries[ids].sum(axis=1)
    if (left < 0).any():
        raise ValueError('Historical roster exceeds salary cap')
    teams = np.asarray(pool['Team'].astype(str))
    games = np.asarray(['|'.join(sorted((str(r.Team), str(r.Opponent)))) for r in pool.itertuples()])
    return {
        # 0=full cap, 1=up to .5% left, ...; 21=more than 10% left.
        'salary_left': np.minimum(21, np.ceil(left / (rules['salary_cap'] * .005))).astype(int),
        'max_team': np.array([max(Counter(teams[row]).values()) for row in ids]),
        'max_game': np.array([max(Counter(games[row]).values()) for row in ids]),
    }


def validate_profile(profile):
    if profile.get('schema') != 1 or profile.get('sport') != 'NBA' or profile.get('platform') != 'DraftKings':
        raise ValueError('Supported NBA DraftKings history profile required')
    date.fromisoformat(profile['date'])
    n = profile['opponent_entries']
    if type(n) is not int or n < 1 or profile.get('fee_bucket') not in {'micro', 'low', 'higher'}:
        raise ValueError('Invalid history sample metadata')
    if profile.get('game_bucket') not in {'small', 'medium', 'large'}:
        raise ValueError('Invalid history game bucket')
    for name in FEATURES:
        counts = profile['histograms'][name]
        limit = 21 if name == 'salary_left' else 8
        if (not counts or any(str(int(k)) != k or not 0 <= int(k) <= limit or
                              type(v) is not int or v < 1 for k, v in counts.items()) or sum(counts.values()) != n):
            raise ValueError('Invalid history histogram: ' + name)
    if not profile.get('contest_id') or not profile.get('source_sha256'):
        raise ValueError('Historical contest provenance required')
    return profile


def load_profiles(directory=PROFILE_DIR):
    return [validate_profile(json.loads(p.read_text())) for p in sorted(Path(directory).glob('*.json'))]


def eligible_profiles(pool, day, fee, profiles=None):
    """Strictly older slates only. Same-day completed contests are not training."""
    if not day:
        return []
    date.fromisoformat(day)
    compatible = []
    seen = set()
    for p in load_profiles() if profiles is None else profiles:
        validate_profile(p)
        key = (p['platform'], p['contest_id'])
        if key in seen:
            raise ValueError('Duplicate history contest')
        seen.add(key)
        if (p['platform'] == rules_for(pool)['platform'] and p['date'] < day and
                p['fee_bucket'] == fee_bucket(fee) and p['game_bucket'] == game_bucket(game_count(pool)) and
                p['opponent_entries'] >= 1000):
            compatible.append(p)
    return compatible


def history_identity(profiles):
    return hashlib.sha256(json.dumps(profiles, sort_keys=True).encode()).hexdigest()


def history_prior(pool, lineups, popularity, profiles):
    """Conservative correction relative to the current popularity-weighted base.

    Each feature contributes equally to a geometric density ratio. Additive
    smoothing, a .5 maximum strength, and [1/4,4] final odds bounds keep a single
    contest from replacing the provider model. These are assumptions, not fitted
    optimal hyperparameters. Duplicate entries count in the training histogram.
    """
    ids = np.asarray(lineups)
    offset = np.zeros(len(ids))
    if not profiles:
        return offset, {'status': 'not applied', 'reason': 'No compatible strictly earlier contest history'}
    features = lineup_features(pool, ids)
    raw = np.asarray(popularity, float)
    if raw.shape != (len(pool),) or not np.isfinite(raw).all() or (raw < 0).any():
        raise ValueError('Valid aligned popularity vector required')
    base = .5 * np.log(np.maximum(raw, .1))[ids].sum(axis=1)
    base = np.exp(base - logsumexp(base))
    n = sum(p['opponent_entries'] for p in profiles)
    strength = .5 * n / (n + 1000)
    coverage = {}
    for name, values in features.items():
        counts = Counter()
        for p in profiles:
            counts.update({int(k): v for k, v in p['histograms'][name].items()})
        bins = 22 if name == 'salary_left' else 9
        observed = np.array([counts.get(i, 0) for i in range(bins)], float)
        current = np.bincount(values, weights=base, minlength=bins)
        target = (observed + 1) / (n + bins)
        ratio = np.clip(target / np.maximum(current, 1e-12), .25, 4)
        offset += np.log(ratio[values]) * strength / len(FEATURES)
        coverage[name] = float(observed[np.unique(values)].sum() / n)
    return np.clip(offset, -np.log(4), np.log(4)), {
        'status': 'applied', 'contests': len(profiles), 'opponent_entries': n,
        'latest_training_date': max(p['date'] for p in profiles),
        'profile_identity': history_identity(profiles), 'strength': strength,
        'features': list(FEATURES), 'observed_feature_mass_on_support': coverage,
        'limitation': 'Estimated habit prior; future-contest accuracy and duplicate-rate improvement unverified',
    }
