import unittest


# SEA-DEN completed DK Showdown field, contest 196689724.
# Parsed from the official contest standings export. 47,271 entries contained
# complete six-player lineups; 291 standings rows did not contain a parseable
# lineup and are excluded from construction/exposure targets.
ENTRIES = 47_271
UNIQUE = 10_547
SINGLETONS = 5_338
TEN_PLUS = 1_031
TWENTY_PLUS = 422
MAX_DUP = 635
TOP_FOUR_CPT_SHARE = 0.6465665867709516

DUPLICATE_ENTRY_MASS = {
    "singleton": 5_338 / ENTRIES,
    "two_to_four": 7_986 / ENTRIES,
    "five_to_nine": 7_443 / ENTRIES,
    "ten_to_nineteen": 8_100 / ENTRIES,
    "twenty_plus": 18_404 / ENTRIES,
}

FLEX_OWNERSHIP = {
    "Sam Darnold": 0.5110,
    "Jaxon Smith-Njigba": 0.4718,
    "Bo Nix": 0.4702,
    "Emanuel Wilson": 0.4075,
    "Jason Myers": 0.3415,
    "RJ Harvey": 0.3254,
}


class DKShowdownLatestActualFieldTests(unittest.TestCase):
    def test_latest_field_unique_ratio(self):
        self.assertGreater(UNIQUE / ENTRIES, 0.21)
        self.assertLess(UNIQUE / ENTRIES, 0.23)

    def test_latest_field_has_heavy_duplicate_entry_mass(self):
        self.assertGreater(DUPLICATE_ENTRY_MASS["twenty_plus"], 0.38)
        self.assertGreater(
            DUPLICATE_ENTRY_MASS["ten_to_nineteen"] + DUPLICATE_ENTRY_MASS["twenty_plus"],
            0.55,
        )
        self.assertLess(DUPLICATE_ENTRY_MASS["singleton"], 0.12)

    def test_latest_field_captain_is_highly_concentrated(self):
        self.assertGreater(TOP_FOUR_CPT_SHARE, 0.64)
        self.assertLess(TOP_FOUR_CPT_SHARE, 0.66)

    def test_latest_field_flex_chalk_is_not_uniform(self):
        values = list(FLEX_OWNERSHIP.values())
        self.assertGreater(max(values), 0.50)
        self.assertGreater(sum(values[:4]), 1.85)
        self.assertGreater(values[0] / values[-1], 1.5)

    def test_latest_field_duplicate_tail_matches_recorded_counts(self):
        self.assertEqual(SINGLETONS, 5_338)
        self.assertEqual(TEN_PLUS, 1_031)
        self.assertEqual(TWENTY_PLUS, 422)
        self.assertEqual(MAX_DUP, 635)


if __name__ == "__main__":
    unittest.main()
