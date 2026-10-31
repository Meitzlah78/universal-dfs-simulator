import unittest
import numpy as np
from simmah_nba_field import ownership_support_diagnostic

class OwnershipSupportDiagnosticTests(unittest.TestCase):
    def test_feasible_and_limited_support(self):
        ids=np.array([list(range(8)),list(range(1,9))])
        target=np.array([50]+[100]*7+[50])
        self.assertEqual(ownership_support_diagnostic(ids,target)['status'],'feasible')
        target=np.array([0]+[100]*7+[100])
        result=ownership_support_diagnostic(ids[:1],target)
        self.assertEqual(result['status'],'support-limited')
        self.assertAlmostEqual(result['minimum_max_error_pct'],100)
