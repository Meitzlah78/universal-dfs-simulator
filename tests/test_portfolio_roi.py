import unittest
import pandas as pd
from simmah_portfolio import portfolio_roi_totals


class PortfolioROITest(unittest.TestCase):
    def test_joint_portfolio_totals_use_all_assigned_entries(self):
        result=portfolio_roi_totals(pd.DataFrame({"Entry Fee ($)":[.25,.25],"Expected Prize ($)":[.2,.8]}))
        self.assertEqual(result,dict(entries=2,fees=.5,winnings=1.,net=.5,roi=100.))

    def test_missing_payout_metrics_are_pending_in_every_format(self):
        for mode in ["Classic","Showdown","Full Roster","Single Game"]:
            result=portfolio_roi_totals(pd.DataFrame({"Mode":[mode]*20}),{"entry_fee":.25})
            self.assertEqual(result["fees"],5.)
            self.assertIsNone(result["roi"])
            self.assertIsNone(result["winnings"])

    def test_partial_estimates_do_not_silently_sum_as_zero(self):
        result=portfolio_roi_totals(pd.DataFrame({"Entry Fee ($)":[1.,1.],"Expected Prize ($)":[2.,None]}))
        self.assertEqual(result["fees"],2.)
        self.assertIsNone(result["roi"])

    def test_empty_free_and_unknown_fee(self):
        self.assertIsNone(portfolio_roi_totals(None)["roi"])
        free=portfolio_roi_totals(pd.DataFrame({"Expected Prize ($)":[1]}),{"entry_fee":0})
        self.assertEqual(free["net"],1)
        self.assertIsNone(free["roi"])
        unknown=portfolio_roi_totals(pd.DataFrame({"Expected Prize ($)":[1]}))
        self.assertIsNone(unknown["fees"])
        self.assertIsNone(unknown["roi"])
