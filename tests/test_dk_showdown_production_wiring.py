import pathlib
import unittest


APP_SOURCE = pathlib.Path("dfs_app.py").read_text(encoding="utf-8")


class DKShowdownProductionWiringTests(unittest.TestCase):
    def test_opponent_builder_uses_calibrated_quality_filter(self):
        self.assertIn("dk_opponent_lineup_means", APP_SOURCE)
        self.assertIn("dk_opponent_quality_acceptance", APP_SOURCE)
        self.assertIn("quality_draw <= quality_acceptance", APP_SOURCE)

    def test_showdown_scoring_uses_multiplicity_aware_bounds(self):
        self.assertIn("contest_unique_idx, contest_multiplicity = np.unique", APP_SOURCE)
        self.assertIn("dk_weighted_score_bounds", APP_SOURCE)
        self.assertIn("batch_field_scores, contest_multiplicity, batch_candidate_scores", APP_SOURCE)

    def test_duplicate_expansion_is_wired_into_generated_field(self):
        self.assertIn("dk_duplicate_expansion_counts", APP_SOURCE)
        self.assertIn("np.repeat", APP_SOURCE)

    def test_portfolio_roi_uses_holdout_simulations_and_tie_splitting(self):
        self.assertIn("holdout_start = selection_n_sims", APP_SOURCE)
        self.assertIn("range(holdout_start, n_sims", APP_SOURCE)
        self.assertIn("_tie_prize_sum", APP_SOURCE)
        self.assertIn("Expected ROI (%)", APP_SOURCE)

    def test_showdown_captain_scoring_multiplier_remains_active(self):
        self.assertIn("scoring_multiplier = 1.5", APP_SOURCE)
        self.assertIn("dk_score_lineup_matrix", APP_SOURCE)


if __name__ == "__main__":
    unittest.main()
