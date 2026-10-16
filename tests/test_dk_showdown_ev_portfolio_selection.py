import pathlib
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "dfs_app.py"


class DKShowdownEVPortfolioSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP_PATH.read_text(encoding="utf-8")

    def test_verified_showdown_payout_uses_expected_roi_for_membership(self):
        source = self.source
        self.assertIn('selection_metric = "Expected ROI (%)" if _selection_has_verified_payout else portfolio_metric', source)
        self.assertIn('str(st.session_state.get("contest_payout_contest_id", "")) == _selection_contest_id', source)
        self.assertIn('.sort_values(selection_metric, ascending=False, kind="stable")', source)

    def test_display_sort_does_not_drive_verified_ev_reselection(self):
        source = self.source
        self.assertIn('st.session_state.get("portfolio_metric_used") != selection_metric', source)
        self.assertIn('st.session_state["portfolio_metric_used"] = selection_metric', source)
        self.assertIn('portfolio_metric, ascending=False, kind="stable"', source)

    def test_ev_selection_keeps_holdout_scoring_separate(self):
        source = self.source
        self.assertIn('selection_n_sims = max(1, n_sims // 2)', source)
        self.assertIn('holdout_start = selection_n_sims', source)
        self.assertIn('for _portfolio_batch_start in range(holdout_start, n_sims, _portfolio_batch_size):', source)

    def test_automatic_diversification_does_not_overpower_core_ev(self):
        self.assertIn('auto_diversification_pct = 90.0', self.source)


if __name__ == "__main__":
    unittest.main()
