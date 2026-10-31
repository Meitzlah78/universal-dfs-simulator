import unittest
import numpy as np
from simmah_nba_field_challenger import fit_bounded_field


class BoundedFieldTests(unittest.TestCase):
    def setUp(self):
        self.ids=np.array([[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]])
        self.targets=np.full(4,50.)
        self.salary=np.full(4,30000.)

    def fit(self,ids=None,**changes):
        args=dict(max_roster_weight=.2,mean_salary_min=59500,
                  tail_salary=58000,tail_fraction_max=.05)
        args.update(changes)
        return fit_bounded_field(self.ids if ids is None else ids,
            self.targets,self.salary,103,**args)

    def test_exact_integer_size_and_concentration(self):
        a=self.fit();b=self.fit()
        self.assertEqual(a['copies'].sum(),103)
        self.assertLessEqual(a['maximum_copies'],21)
        self.assertGreaterEqual(a['unique_rosters'],5)
        self.assertTrue(np.array_equal(a['copies'],b['copies']))
        self.assertLessEqual(a['weights'].max(),.2+1e-10)
        self.assertAlmostEqual(a['integer_mean_salary'],60000)
        self.assertEqual(a['integer_tail_fraction'],0)
        self.assertFalse(a['live_enabled'])

    def test_impossible_cap_fails(self):
        with self.assertRaisesRegex(ValueError,'cannot cover'):
            self.fit(max_roster_weight=.1)

    def test_infeasible_salary_fails(self):
        with self.assertRaisesRegex(ValueError,'fit unavailable'):
            self.fit(mean_salary_min=61000)

    def test_canonical_duplicate_rejected(self):
        ids=self.ids.copy();ids[-1]=[1,0]
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.fit(ids)

    def test_missing_target_not_silently_zero(self):
        self.targets[0]=np.nan
        with self.assertRaisesRegex(ValueError,'finite'):
            self.fit()


if __name__=='__main__':unittest.main()
