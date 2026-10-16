import unittest


# Two completed large-field DK Showdown contests. These ratios are intentionally
# broad cross-slate targets: the exact chalk lineup changes, but a realistic
# public field must reproduce a substantial duplicate tail.
FIELDS = (
    {"entries": 59453, "unique": 12029, "ten_plus": 1340, "twenty_plus": 569, "max_dup": 397},
    {"entries": 47271, "unique": 10547, "ten_plus": 1031, "twenty_plus": 422, "max_dup": 635},
)


class DKShowdownDuplicateCalibrationTests(unittest.TestCase):
    def test_real_duplicate_tail_target_band(self):
        unique_rates = [f["unique"] / f["entries"] for f in FIELDS]
        ten_plus_rates = [f["ten_plus"] / f["unique"] for f in FIELDS]
        twenty_plus_rates = [f["twenty_plus"] / f["unique"] for f in FIELDS]

        # Only about one-fifth to one-quarter as many unique constructions as
        # total entries: replacement expansion is required, not a unique field.
        for rate in unique_rates:
            self.assertGreater(rate, 0.19)
            self.assertLess(rate, 0.23)

        # Roughly one in ten unique constructions appears at least ten times.
        for rate in ten_plus_rates:
            self.assertGreater(rate, 0.09)
            self.assertLess(rate, 0.12)

        # Roughly 4-5% of unique constructions appear at least twenty times.
        for rate in twenty_plus_rates:
            self.assertGreater(rate, 0.035)
            self.assertLess(rate, 0.055)

        # Both contests also contain an extreme chalk tail measured in hundreds.
        for field in FIELDS:
            self.assertGreater(field["max_dup"], 300)

    def test_cross_slate_duplicate_shape_is_stable_enough_to_calibrate(self):
        first, second = FIELDS
        first_ten = first["ten_plus"] / first["unique"]
        second_ten = second["ten_plus"] / second["unique"]
        first_twenty = first["twenty_plus"] / first["unique"]
        second_twenty = second["twenty_plus"] / second["unique"]
        self.assertLess(abs(first_ten - second_ten), 0.02)
        self.assertLess(abs(first_twenty - second_twenty), 0.01)


if __name__ == "__main__":
    unittest.main()
