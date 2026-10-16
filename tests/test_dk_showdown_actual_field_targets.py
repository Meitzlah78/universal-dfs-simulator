import unittest


# Completed large-field DK Showdown contests used to keep field-model changes
# grounded in real entry behavior instead of a single slate or hand-tuned curve.
ACTUAL_SHOWDOWN_FIELDS = {
    "BUF_LAR_196537800": {
        "entries": 59453,
        "unique_lineups": 12029,
        "median_duplicates": 2,
        "max_duplicates": 397,
        "lineups_10_plus": 1340,
        "lineups_20_plus": 569,
    },
    "2026_10_15_196689724": {
        "entries": 47271,
        "unique_lineups": 10547,
        "singletons": 5338,
        "max_duplicates": 635,
        "lineups_10_plus": 1031,
        "lineups_20_plus": 422,
    },
}


class ActualDKShowdownFieldTargetTests(unittest.TestCase):
    def test_real_fields_have_consistent_large_field_shape(self):
        for target in ACTUAL_SHOWDOWN_FIELDS.values():
            self.assertGreater(target["entries"], 40_000)
            unique_rate = target["unique_lineups"] / target["entries"]
            self.assertGreater(unique_rate, 0.15)
            self.assertLess(unique_rate, 0.30)
            self.assertGreater(target["max_duplicates"], 300)
            self.assertGreater(target["lineups_10_plus"], 900)
            self.assertGreater(target["lineups_20_plus"], 350)

    def test_two_fields_are_close_enough_for_cross_slate_calibration(self):
        older = ACTUAL_SHOWDOWN_FIELDS["BUF_LAR_196537800"]
        newer = ACTUAL_SHOWDOWN_FIELDS["2026_10_15_196689724"]
        older_unique_rate = older["unique_lineups"] / older["entries"]
        newer_unique_rate = newer["unique_lineups"] / newer["entries"]
        # The exact slate changes the tail, but both real fields put only about
        # one-fifth of entries into unique constructions. Calibration should
        # therefore target a range, not memorize one contest's duplicate curve.
        self.assertLess(abs(older_unique_rate - newer_unique_rate), 0.04)

        older_10_rate = older["lineups_10_plus"] / older["unique_lineups"]
        newer_10_rate = newer["lineups_10_plus"] / newer["unique_lineups"]
        self.assertLess(abs(older_10_rate - newer_10_rate), 0.04)


if __name__ == "__main__":
    unittest.main()
