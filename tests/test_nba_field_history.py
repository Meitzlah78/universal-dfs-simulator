import copy
import csv
import io
import unittest
from unittest.mock import patch
import numpy as np

from simmah_nba_field_history import (eligible_profiles, history_prior, lineup_features,
                                     load_profiles, validate_profile)
from simmah_nba_field import build_field, sample_popularity_field
from simmah_nba_import import read_template
from scripts.import_nba_field_history import import_contest
from test_nba_draftkings import template
from simmah_nba_candidates import build_candidates
from simmah_nba_pipeline import run_pipeline


class NBAHistoryTests(unittest.TestCase):
    def setUp(self):
        self.pool = read_template(template())['players']
        self.pool['Projection'] = 30.
        self.pool['Eligible'] = True
        # Deliberately heterogeneous spending to observe a learned habit.
        self.pool['Salary'] = 3000 + np.arange(40) * 90
        self.ids = build_candidates(self.pool, np.random.default_rng(7).normal(30, 5, (80, 40)),
                                    target=160, seed=8)['indices']
        self.profile = {
            'schema': 1, 'sport': 'NBA', 'platform': 'DraftKings', 'contest_id': 'earlier',
            'date': '2026-10-19', 'fee_bucket': 'micro', 'game_bucket': 'small',
            'opponent_entries': 2000, 'source_sha256': 'fixture',
            'histograms': {'salary_left': {'1': 2000}, 'max_team': {'3': 2000}, 'max_game': {'5': 2000}},
        }

    def test_strict_date_platform_stakes_and_slate_size(self):
        p = self.profile
        self.assertEqual(eligible_profiles(self.pool, '2026-10-20', .25, [p]), [p])
        for day in ['2026-10-19', '2026-10-18', None]:
            self.assertEqual(eligible_profiles(self.pool, day, .25, [p]), [])
        self.assertEqual(eligible_profiles(self.pool, '2026-10-20', 25, [p]), [])
        self.pool.attrs['platform'] = 'FanDuel'
        self.assertEqual(eligible_profiles(self.pool, '2026-10-20', .25, [p]), [])

    def test_history_offsets_change_probabilities_but_preserve_targets(self):
        prior, report = history_prior(self.pool, self.ids, np.ones(40), [self.profile])
        self.assertEqual(report['status'], 'applied')
        self.assertGreater(np.ptp(prior), 0)
        self.assertLessEqual(abs(prior).max(), np.log(4))
        original = sample_popularity_field(self.ids, np.ones(40), 10000, source='fixture')
        shaped = sample_popularity_field(self.ids, np.ones(40), 10000, source='fixture', log_prior=prior)
        self.assertFalse(np.array_equal(original['copies'], shaped['copies']))
        targets = np.bincount(self.ids.ravel(), minlength=40) * 100 / len(self.ids)
        fitted = build_field(self.ids, targets, 10000, source='fixture', log_prior=prior, max_iterations=300)
        self.assertLess(fitted['max_expected_error_pct'], .1)
        np.testing.assert_array_equal(fitted['ownership_target'], targets)
        self.assertEqual(shaped['copies'].sum(), 10000)

    def test_invalid_prior_and_profile_rejected(self):
        for prior in [np.zeros(1), np.full(len(self.ids), np.nan)]:
            with self.assertRaises(ValueError):
                sample_popularity_field(self.ids, np.ones(40), 10, source='fixture', log_prior=prior)
        bad = copy.deepcopy(self.profile); bad['histograms']['max_team']['3'] -= 1
        with self.assertRaises(ValueError): validate_profile(bad)
        with self.assertRaises(ValueError):
            eligible_profiles(self.pool, '2026-10-20', .25, [self.profile, self.profile])

    def test_canonical_dedup_preserves_prior_alignment(self):
        row = self.ids[:1]
        base = sample_popularity_field(row, np.ones(40), 10, source='fixture', log_prior=[.3])
        repeated = sample_popularity_field(np.vstack([row, row[:, ::-1]]), np.ones(40), 10,
                                          source='fixture', log_prior=[.3, .3])
        np.testing.assert_array_equal(base['indices'], repeated['indices'])
        np.testing.assert_array_equal(base['copies'], repeated['copies'])

    def test_real_pipeline_applies_earlier_profile_and_blocks_same_day(self):
        def draw(n, seed): return np.random.default_rng(seed).gamma(5, 6, (n, len(self.pool)))
        arguments = dict(simulations=20, candidate_target=20, field_support_target=80,
                         ownership_mode='relative popularity', history_profiles=[self.profile])
        for day, expected in [('2026-10-20', 'applied'), ('2026-10-19', 'not applied')]:
            result = run_pipeline(self.pool, draw, np.ones(40), 'fixture', [10]+[0]*100, .25, 2,
                                  slate_day=day, **arguments)
            self.assertEqual(result['field']['contest_history']['status'], expected)
            self.assertEqual(result['field']['copies'].sum(), 100)

    def test_importer_ignores_scores_and_slot_percentage_side_table(self):
        # Use original fixed salaries and legal roster from the matching template.
        pool = read_template(template())['players']; pool['Projection'] = 30.
        ids = build_candidates(pool, np.random.default_rng(2).random((10, 40)), target=1)['indices'][0]
        slots = ('PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL')
        lineup = ' '.join(s+' '+pool.iloc[i]['Name'] for s, i in zip(slots, ids))
        def export(points='0', unfinished=False):
            out = io.StringIO(); writer = csv.writer(out)
            writer.writerow(['EntryId', 'TimeRemaining', 'Lineup', 'Points', 'Player', '%Drafted'])
            for entry in ['100', '101', '102', '200', '201']:
                writer.writerow([entry, '1' if unfinished else '0', lineup, points, '', ''])
            writer.writerow(['202', '0', '', '', '', ''])
            writer.writerow(['', '', '', '', 'Player 1', '99%'])
            return out.getvalue().encode()
        p = import_contest(export(), template(), '196711762', 6)
        q = import_contest(export('999'), template(), '196711762', 6)
        self.assertEqual(p['histograms'], q['histograms'])
        self.assertEqual(p['opponent_entries'], 2)
        self.assertEqual(p['unique_opponent_rosters'], 1)
        self.assertEqual(p['excluded_user_entries'], 3)
        self.assertEqual(p['unavailable_lineup_entries'], 1)
        with self.assertRaises(ValueError): import_contest(export(unfinished=True), template(), '196711762', 6)
        with self.assertRaises(ValueError): import_contest(export(), template(), '196711762', 7)

    def test_bundled_profile_is_anonymous_and_not_used_on_its_own_date(self):
        profiles = load_profiles()
        self.assertEqual(len(profiles), 1)
        p = profiles[0]
        self.assertEqual(p['opponent_entries'], 16712)
        self.assertEqual(p['unavailable_lineup_entries'], 80)
        self.assertEqual(p['excluded_user_entries'], 20)
        self.assertFalse({'names', 'players', 'points', 'entry_ids'} & p.keys())
        self.assertEqual(eligible_profiles(self.pool, p['date'], .25, profiles), [])

    def test_replay_detects_ownership_pair_and_duplicate_errors(self):
        from scripts.replay_nba_opponent_field import compare_field
        exact = compare_field(self.pool, self.ids, self.ids, np.ones(len(self.ids)))
        self.assertEqual(exact['ownership_mae_pp'], 0)
        self.assertEqual(exact['pair_inclusion_mae_pp'], 0)
        self.assertEqual(sum(exact['feature_total_variation'].values()), 0)
        changed = compare_field(self.pool, self.ids, self.ids[:1], [len(self.ids)])
        self.assertGreater(changed['ownership_mae_pp'], 0)
        self.assertGreater(changed['pair_inclusion_mae_pp'], 0)
        self.assertGreater(changed['modeled_duplicate_entry_fraction'], 0)
        with self.assertRaises(ValueError): compare_field(self.pool, self.ids, self.ids, [1])

    def test_history_invalidates_saved_build_identity(self):
        from simmah_nba_ui import input_identity
        original = input_identity(self.pool, [], {}, 0)
        learned = input_identity(self.pool, [], {}, 0, history_profiles=[self.profile])
        self.assertNotEqual(original, learned)

    def test_projected_fallback_keeps_history_prior(self):
        import simmah_nba_pipeline as pipeline
        def draw(n, seed): return np.random.default_rng(seed).random((n, len(self.pool)))
        with patch.object(pipeline, 'build_field', return_value={'max_expected_error_pct': 99}), \
             patch.object(pipeline, 'ownership_support_diagnostic', return_value={'status': 'inconclusive'}):
            result = run_pipeline(self.pool, draw, np.full(40, 20.), 'fixture', [10]+[0]*100, .25, 2,
                simulations=20, candidate_target=20, field_support_target=80,
                history_profiles=[self.profile], slate_day='2026-10-20')
        self.assertEqual(result['field']['contest_history']['status'], 'applied')
        self.assertIn('fallback_mode', result['field'])
        np.testing.assert_array_equal(result['field']['ownership_target'], np.full(40, 20.))


if __name__ == '__main__': unittest.main()
