"""Exact contest metadata must reach both candidate and portfolio scoring."""
import ast
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from simmah_contests import payout_vector, evaluate_contest

class HailMaryContestTests(unittest.TestCase):
    def resolve(self, contest):
        tree = ast.parse(Path('dfs_app.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'full_roster_contest_parameters')
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'dfs_app.py', 'exec'), namespace)
        return namespace[node.name](contest, 10000)

    def test_verified_capacity_overrides_partial_registrations(self):
        spec = self.resolve({'id': '135541-281148543', 'your_entries': 20, 'field_size': 16692})
        self.assertEqual(spec['field_size'], 95808)
        self.assertEqual(spec['fee'], .25)
        self.assertTrue(spec['payouts_known'])
        payouts = payout_vector(spec['field_size'], spec['tiers'])
        self.assertEqual(np.count_nonzero(payouts), 28750)
        self.assertAlmostEqual(payouts.sum(), 20000)
        self.assertEqual(payouts[0], 500)

    def test_other_contests_do_not_inherit_verified_payouts(self):
        spec = self.resolve({'id': 'other', 'entry_fee': .25, 'your_entries': 20})
        self.assertFalse(spec['payouts_known'])
        self.assertEqual(spec['tiers'], [])

    def test_scoring_uses_full_capacity_and_positive_prize(self):
        spec = self.resolve({'id': '135541-281148543', 'your_entries': 20})
        slots = ['MVP', 'FLEX']
        candidate = pd.DataFrame([['A', 'B']], columns=slots)
        field = pd.DataFrame([['B', 'A']] * 10000, columns=slots)
        results = evaluate_contest(pd.DataFrame({'A': [20.], 'B': [1.]}), candidate, field,
            slots, spec['field_size'], spec['tiers'], spec['fee'], multipliers=[1.5, 1])
        self.assertEqual(float(results.iloc[0]['Expected Prize ($)']), 500)
        self.assertGreater(float(results.iloc[0]['Expected ROI (%)']), 0)

if __name__ == '__main__':
    unittest.main()
