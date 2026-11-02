import unittest
import pandas as pd
from simmah_player_exposure import player_exposure


class ExposureTests(unittest.TestCase):
    def test_roles_use_entry_denominator_and_repeated_entries(self):
        for role in ("Captain", "MVP"):
            frame = pd.DataFrame({role: ["A", "A", "B"], "FLEX1": ["B", "B", "A"],
                                  "FLEX2": ["C", "C", None]})
            result = player_exposure(frame, [role, "FLEX1", "FLEX2"], role).set_index("Player")
            self.assertEqual(result.loc["A", "Overall entries"], 3)
            self.assertEqual(result.loc["A", role + " entries"], 2)
            self.assertAlmostEqual(result.loc["A", "FLEX %"], 100 / 3)
            self.assertAlmostEqual(result[role + " %"].sum(), 100)
            self.assertEqual(result.loc["C", "FLEX entries"], 2)

    def test_full_roster_and_empty(self):
        result = player_exposure(pd.DataFrame({"QB": ["A"], "FLEX": ["B"]}), ["QB", "FLEX"])
        self.assertEqual(result["Overall %"].tolist(), [100, 100])
        self.assertNotIn("FLEX %", result)
        self.assertTrue(player_exposure(pd.DataFrame(), ["Captain"], "Captain").empty)


if __name__ == "__main__":
    unittest.main()
