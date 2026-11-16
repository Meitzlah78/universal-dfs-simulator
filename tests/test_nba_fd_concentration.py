import itertools
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_selector_budget import select_quality_budget, CapConflict, milp
from simmah_nba_contest import select_entries, selection_key


class FDConcentrationTests(unittest.TestCase):
    def test_exact_objective_and_quality_floor_match_exhaustive_search(self):
        rng = np.random.default_rng(37)
        rosters = list(itertools.combinations('abcdefg', 3))
        rng.shuffle(rosters)
        rows = pd.DataFrame(rosters[:16], columns=['a', 'b', 'c'])
        rows['q'] = rng.uniform(7, 10, len(rows))
        controls = {'a': {'Max Exposure %': 50}, 'g': {'Min Exposure %': 25}}
        feasible = []
        for ids in itertools.combinations(range(len(rows)), 4):
            counts = pd.Series(rows.iloc[list(ids)][['a', 'b', 'c']].to_numpy().ravel()).value_counts()
            if counts.get('a', 0) <= 2 and counts.get('g', 0) >= 1:
                feasible.append((rows.iloc[list(ids)].q.sum(), (counts ** 2).sum()))
        optimum = max(q for q, _ in feasible)
        for budget in [0., .0125, .025, .05]:
            floor = optimum * (1 - budget)
            best = min(c for q, c in feasible if q >= floor - 1e-9)
            for tighten in [False, True]:
                selected = select_quality_budget(rows, ['a', 'b', 'c'], 4,
                    controls=controls, automatic_max=100, quality_metric='q',
                    quality_loss=budget, tighten=tighten)
                self.assertAlmostEqual(selected.attrs['quality_optimum'], optimum)
                self.assertGreaterEqual(selected.q.sum() + 1e-9, floor)
                self.assertEqual(selected.attrs['concentration_after'], best)
                self.assertTrue(selected.attrs['diversity_optimal'])
                self.assertEqual(selected.attrs['concentration_mip_gap'], 0)

    def test_manual_minimum_can_require_low_quality_candidate(self):
        rows = pd.DataFrame({'a': ['a', 'a', 'b', 'x'], 'b': ['b', 'c', 'c', 'y'], 'q': [10., 9., 8., 1.]})
        selected = select_quality_budget(rows, ['a', 'b'], 2,
            controls={'x': {'Min Exposure %': 50}}, automatic_max=100,
            quality_metric='q', tighten=True)
        self.assertIn('x', selected[['a', 'b']].to_numpy())
        self.assertAlmostEqual(selected.attrs['quality_optimum'], 11.)

    def test_fixed_counts_fades_and_duplicate_rosters(self):
        rows = pd.DataFrame({'a': ['a', 'a', 'x', 'b'], 'b': ['b', 'b', 'y', 'c'], 'q': [10., 10., 9., 8.]})
        # Only one distinct roster has a, so the lock is infeasible.
        with self.assertRaises(CapConflict):
            select_quality_budget(rows, ['a', 'b'], 2,
                controls={'a': {'Lock': True}, 'x': {'Fade': True}},
                automatic_max=100, quality_metric='q', tighten=True)

    def test_timeout_retains_valid_certified_optimum(self):
        rows = pd.DataFrame({'a': ['a', 'a', 'x'], 'b': ['b', 'c', 'y'], 'q': [10., 9., 8.]})
        calls = []
        def solve(*args, **kwargs):
            calls.append(1)
            return milp(*args, **kwargs) if len(calls) == 1 else SimpleNamespace(status=1, x=None, mip_gap=None)
        with patch('simmah_selector_budget.milp', side_effect=solve):
            selected = select_quality_budget(rows, ['a', 'b'], 2,
                automatic_max=100, quality_metric='q', tighten=True)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected.attrs['actual_quality_loss'], 0.)
        self.assertFalse(selected.attrs['diversity_optimal'])

    def test_one_entry_and_zero_quality_candidates(self):
        rows = pd.DataFrame({'a': ['a', 'b', 'c'], 'q': [10., 0., 0.]})
        selected = select_quality_budget(rows, ['a'], 1,
            automatic_max=100, quality_metric='q', tighten=True)
        self.assertEqual(selected.a.tolist(), ['a'])
        self.assertEqual(selected.attrs['retained_candidates'], 1)

    def test_nba_routing_and_existing_diversity_mapping(self):
        for platform, slots in [('DraftKings', 8), ('FanDuel', 9)]:
            pool = pd.DataFrame({'Player ID': [str(i) for i in range(slots * 3)],
                                 'Name': ['P' + str(i) for i in range(slots * 3)]})
            pool.attrs.update(platform=platform, nba_uncapped=True)
            candidates = np.arange(slots * 3).reshape(3, slots)
            report = pd.DataFrame({'Top 1%': [10., 9., 8.]})
            for diversity in [0, 25, 50, 100]:
                with patch('simmah_nba_contest.select_quality_budget', wraps=select_quality_budget) as solve:
                    selected = select_entries(pool, candidates, report, 2, diversity=diversity)
                self.assertEqual(solve.call_args.kwargs['tighten'], platform == 'FanDuel')
                self.assertEqual(selected.attrs['quality_loss_budget'], .05 if diversity else 0.)
            self.assertEqual(selection_key(pool, candidates, report, 2, 25, 'Top 1%'),
                             selection_key(pool, candidates, report, 2, 100, 'Top 1%'))
            self.assertNotEqual(selection_key(pool, candidates, report, 2, 0, 'Top 1%'),
                                selection_key(pool, candidates, report, 2, 100, 'Top 1%'))

    def test_large_fd_portfolios_keep_original_formulation(self):
        slots = ['PG', 'SG', 'SF', 'PF', 'C', 'GF', 'FC', 'UTIL1', 'UTIL2']
        pool = pd.DataFrame({'Player ID': [str(i) for i in range(27 * 9)]})
        pool.attrs.update(platform='FanDuel', nba_uncapped=True)
        indices = np.arange(27 * 9).reshape(27, 9)
        report = pd.DataFrame({'Top 1%': np.arange(27, 0, -1, dtype=float)})
        for count, expected in [(25, True), (26, False)]:
            selected = pd.DataFrame(indices[:count].astype(str), columns=slots)
            with patch('simmah_nba_contest.select_quality_budget', return_value=selected) as solve:
                select_entries(pool, indices, report, count, diversity=100)
            self.assertEqual(solve.call_args.kwargs['tighten'], expected)
            current_key = selection_key(pool, indices, report, count, 100, 'Top 1%')
            with patch('simmah_nba_contest._tighten_concentration', return_value=False):
                legacy_key = selection_key(pool, indices, report, count, 100, 'Top 1%')
            self.assertEqual(current_key == legacy_key, not expected)


if __name__ == '__main__':
    unittest.main()
