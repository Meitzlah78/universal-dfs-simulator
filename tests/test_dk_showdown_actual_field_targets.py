import unittest


# Completed DK Showdown contests used to keep field-model changes grounded in
# real entry behavior instead of a single slate or hand-tuned curve.  Store
# normalized entry-mass metrics as well as construction counts so contests of
# different sizes can be compared without assuming every field is 40k+ entries.
ACTUAL_SHOWDOWN_FIELDS = {
    "BUF_LAR_196537800": {
        "entries": 59004,
        "unique_lineups": 12029,
        "median_duplicates": 2,
        "max_duplicates": 397,
        "singletons": 5706,
        "singleton_entry_mass": 0.0967053081,
        "lineups_10_plus": 1340,
        "entry_mass_10_plus": 0.5793166565,
        "lineups_20_plus": 569,
        "entry_mass_20_plus": 0.4032268999,
    },
    "SEA_DEN_196689724": {
        "entries": 47271,
        "unique_lineups": 10547,
        "median_duplicates": 1,
        "max_duplicates": 635,
        "singletons": 5338,
        "singleton_entry_mass": 0.1129233568,
        "lineups_10_plus": 1031,
        "entry_mass_10_plus": 0.5606820249,
        "lineups_20_plus": 422,
        "entry_mass_20_plus": 0.3893296101,
    },
    "BAL_ATL_196537727": {
        "entries": 35394,
        "unique_lineups": 8369,
        "median_duplicates": 2,
        "max_duplicates": 211,
        "singletons": 4069,
        "singleton_entry_mass": 0.1149629881,
        "lineups_10_plus": 817,
        "entry_mass_10_plus": 0.5152003164,
        "lineups_20_plus": 287,
        "entry_mass_20_plus": 0.3178222298,
    },
}


class ActualDKShowdownFieldTargetTests(unittest.TestCase):
    def test_real_fields_have_consistent_normalized_shape(self):
        for target in ACTUAL_SHOWDOWN_FIELDS.values():
            self.assertGreater(target["entries"], 30_000)
            unique_rate = target["unique_lineups"] / target["entries"]
            self.assertGreater(unique_rate, 0.15)
            self.assertLess(unique_rate, 0.30)
            self.assertIn(target["median_duplicates"], (1, 2))
            self.assertGreater(target["max_duplicates"], 150)

            # Across three completed contests, roughly one-tenth of all entries
            # are singleton constructions while most entry mass is concentrated
            # in constructions duplicated at least ten times.
            self.assertGreater(target["singleton_entry_mass"], 0.08)
            self.assertLess(target["singleton_entry_mass"], 0.13)
            self.assertGreater(target["entry_mass_10_plus"], 0.50)
            self.assertLess(target["entry_mass_10_plus"], 0.62)
            self.assertGreater(target["entry_mass_20_plus"], 0.30)
            self.assertLess(target["entry_mass_20_plus"], 0.45)

    def test_cross_slate_calibration_uses_ranges_not_one_contest(self):
        unique_rates = [
            target["unique_lineups"] / target["entries"]
            for target in ACTUAL_SHOWDOWN_FIELDS.values()
        ]
        singleton_masses = [
            target["singleton_entry_mass"]
            for target in ACTUAL_SHOWDOWN_FIELDS.values()
        ]
        mass_10_plus = [
            target["entry_mass_10_plus"]
            for target in ACTUAL_SHOWDOWN_FIELDS.values()
        ]

        self.assertLess(max(unique_rates) - min(unique_rates), 0.04)
        self.assertLess(max(singleton_masses) - min(singleton_masses), 0.025)
        self.assertLess(max(mass_10_plus) - min(mass_10_plus), 0.07)


if __name__ == "__main__":
    unittest.main()
