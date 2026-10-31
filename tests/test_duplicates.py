import unittest

import pandas as pd

from simmah_duplicates import showdown_opponent_copies


class DuplicateTests(unittest.TestCase):
    slots = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]

    def test_counts_opponents_only_and_respects_captain(self):
        portfolio = pd.DataFrame([
            ["A", "B", "C", "D", "E", "F"],
            ["B", "A", "C", "D", "E", "F"],
            ["X", "B", "C", "D", "E", "F"]], columns=self.slots, index=[4, 6, 8])
        field = pd.DataFrame([
            ["A", "F", "E", "D", "C", "B"],
            [" A ", "B", "C", "D", "E", "F"],
            ["B", "A", "C", "D", "E", "F"]], columns=self.slots)
        result = showdown_opponent_copies(portfolio, field)
        self.assertEqual(result.tolist(), [2, 1, 0])
        self.assertEqual(result.index.tolist(), [4, 6, 8])

    def test_missing_field_is_pending_but_empty_field_has_zero_copies(self):
        portfolio = pd.DataFrame([["A", "B", "C", "D", "E", "F"]], columns=self.slots)
        self.assertTrue(showdown_opponent_copies(portfolio, None).isna().all())
        self.assertEqual(showdown_opponent_copies(portfolio, pd.DataFrame(columns=self.slots)).tolist(), [0])


if __name__ == "__main__":
    unittest.main()
