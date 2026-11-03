"""Retrospective chronological forecast audit; never modifies active models.

Fits one fixed, shrinkage-weighted additive point-bias correction per platform
on earlier dates and evaluates the latest date untouched. Site contexts from
the same matchup are NOT independent games. This cannot certify raw-stat roles,
variance, correlations or full-engine model promotion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd


def metrics(frame, column):
    usable = frame.loc[np.isfinite(pd.to_numeric(frame[column], errors='coerce'))]
    if usable.empty:
        return {'rows': 0}
    error = usable[column].astype(float).to_numpy() - usable.actual_points.to_numpy(float)
    return {'rows': len(usable), 'mae': float(np.abs(error).mean()),
            'rmse': float(np.sqrt(np.square(error).mean())), 'bias': float(error.mean())}


def audit(root):
    root = Path(root)
    rows, sources = [], []
    for path in sorted((root / 'nfl_validation').rglob('*.json')):
        if path.name != 'projection_actuals.json' and not path.name.startswith('completed_contest_'):
            continue
        raw = path.read_bytes()
        value = json.loads(raw)
        if path.name == 'projection_actuals.json':
            records = value['rows']
        else:
            # Both documented site entry IDs and matched frozen export identify
            # the platform; no cross-site fantasy-score conversion is performed.
            platform = 'FanDuel' if '-' in value['contest_id'] else 'DraftKings'
            records = [dict(row, platform=platform, contest_id=value['contest_id'],
                            slate_date=value['slate_date']) for row in value['projection_actuals']]
        rows.extend(records)
        sources.append({'path': str(path.relative_to(root)),
                        'sha256': hashlib.sha256(raw).hexdigest(), 'rows': len(records)})
    if not rows:
        raise ValueError('No frozen forecast/actual pairs')
    frame = pd.DataFrame(rows)
    for column in ('projection', 'sim_mean', 'actual_points'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    if not np.isfinite(frame[['projection', 'actual_points']]).all().all():
        raise ValueError('Missing or nonfinite forecast/actual pair')
    key = ['platform', 'slate_date', 'player']
    if frame.duplicated(key).any():
        raise ValueError('Ambiguous repeated player/platform/date; resolve before auditing')
    dates = sorted(frame.slate_date.unique())
    if len(dates) < 2:
        raise ValueError('Need an earlier fitting date and later untouched date')
    holdout_date = dates[-1]
    train, test = frame[frame.slate_date < holdout_date].copy(), frame[frame.slate_date == holdout_date].copy()
    assert train.slate_date.max() < test.slate_date.min()
    result = {'schema': 1, 'status': 'retrospective validation completed; no model activated',
              'sources': sources, 'rows': len(frame), 'training_dates': dates[:-1],
              'holdout_date': holdout_date, 'training_rows': len(train), 'holdout_rows': len(test),
              'candidate_protocol': {'family': 'platform-specific additive point-bias correction',
                 'prior_zero_bias_observations': 20, 'prediction_floor': 0,
                 'parameters_fit_only_on_earlier_dates': True,
                 'protocol_was_not_preregistered': True}, 'platforms': {}}
    for platform in sorted(frame.platform.unique()):
        earlier, later = train[train.platform == platform], test[test.platform == platform].copy()
        if earlier.empty or later.empty:
            continue
        correction = float((earlier.actual_points - earlier.projection).sum() / (len(earlier) + 20))
        later['candidate'] = np.maximum(0, later.projection + correction)
        baseline, candidate = metrics(later, 'projection'), metrics(later, 'candidate')
        result['platforms'][platform] = {'training_rows': len(earlier),
            'fitted_point_adjustment': correction, 'holdout_projection': baseline,
            'holdout_candidate': candidate, 'holdout_sim_mean': metrics(later, 'sim_mean'),
            'holdout_mae_change': candidate['mae'] - baseline['mae'],
            'holdout_rmse_change': candidate['rmse'] - baseline['rmse'],
            'improves_both_point_metrics': candidate['mae'] < baseline['mae'] and candidate['rmse'] < baseline['rmse'],
            'all_dates_projection': metrics(frame[frame.platform == platform], 'projection'),
            'all_dates_sim_mean': metrics(frame[frame.platform == platform], 'sim_mean')}
    result['promotion'] = {'accepted': False,
        'reasons': ['Latest uploaded holdout is one CHI/SEA game; DK and FD are two scoring contexts, not independent games.',
                    'Bias-only fantasy-score diagnostics cannot pass existing full-engine raw-stat and joint-distribution gates.',
                    'Existing full-game promotion requires at least 20 independent complete frozen game cases with explicit raw actuals; these standings do not supply those raw actuals.',
                    'Retrospective, non-preregistered test: this date cannot become a repeatedly tuned final validation set.'],
        'active_models_modified': False}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', default='data')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = audit(args.data_root)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
