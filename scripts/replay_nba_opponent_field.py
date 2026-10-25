"""Compare a SAVED modeled opponent field with a completed matching DK field.

Pass the original DOWNLOAD OPPONENT FIELD CSV, not a rebuilt post-game forecast.
Descriptive replay only: an in-sample profile cannot prove predictive gain.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.import_nba_field_history import import_contest
from simmah_nba_field_history import lineup_features
from simmah_nba_rules import rules_for
from simmah_nba_rosters import validate_lineup


def compare_field(pool, observed, modeled, copies):
    copies = np.asarray(copies, float)
    if copies.shape != (len(modeled),) or not np.isfinite(copies).all() or (copies < 1).any() or (copies != np.floor(copies)).any():
        raise ValueError('Positive integer copies aligned to modeled rosters required')
    actual = lineup_features(pool, observed); predicted = lineup_features(pool, modeled)
    n = len(pool)
    def inclusion(ids, weights):
        a = np.zeros((len(ids), n))
        a[np.arange(len(ids))[:, None], ids] = 1
        return weights @ a / weights.sum(), a.T @ (a * weights[:, None]) / weights.sum()
    own, pairs = inclusion(observed, np.ones(len(observed)))
    pred_own, pred_pairs = inclusion(modeled, copies)
    def duplicates(ids, weights):
        counts = Counter()
        for row, weight in zip(ids, weights): counts[tuple(sorted(row))] += int(weight)
        return 1-len(counts)/sum(counts.values())
    return {
        'observed_entries': len(observed), 'modeled_entries': int(copies.sum()),
        'ownership_mae_pp': float(np.mean(abs(own-pred_own))*100),
        'pair_inclusion_mae_pp': float(abs(pairs-pred_pairs)[np.triu_indices(n, 1)].mean()*100),
        'feature_total_variation': {k: float(sum(abs(
            np.bincount(actual[k], minlength=22)/len(observed) -
            np.bincount(predicted[k], weights=copies, minlength=22)/copies.sum()))/2) for k in actual},
        'observed_duplicate_entry_fraction': duplicates(observed, np.ones(len(observed))),
        'modeled_duplicate_entry_fraction': duplicates(modeled, copies),
        'limitation': 'Descriptive replay; compare saved before-tip fields on independent later contests for predictive evidence',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standings', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--contest', required=True)
    parser.add_argument('--expected-entries', type=int, required=True)
    parser.add_argument('--field', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    profile, pool, observed = import_contest(a.standings.read_bytes(), a.template.read_bytes(),
        a.contest, a.expected_entries, return_lineups=True)
    field = pd.read_csv(a.field, dtype=str)
    rules = rules_for(pool); slots = list(rules['slots'])
    if not set(slots+['Copies']) <= set(field): raise ValueError('Saved opponent-field export required')
    lookup = {pid: i for i, pid in enumerate(pool['Player ID'])}
    ids = []
    for row in field[slots].itertuples(index=False, name=None):
        validate_lineup(pool, list(row), salary_cap=rules['salary_cap'],
            max_from_team=rules['max_from_team'], require_projections=False)
        ids.append([lookup[v] for v in row])
    report = compare_field(pool, observed, np.asarray(ids), pd.to_numeric(field['Copies']).to_numpy())
    report['contest_id'] = profile['contest_id']
    report['unavailable_lineup_entries'] = profile['unavailable_lineup_entries']
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
