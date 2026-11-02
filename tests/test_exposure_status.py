import unittest
import pandas as pd
from simmah_player_exposure import exposure_status
from simmah_exposure_limits import validate_exposure_limits

class ExposureStatusTests(unittest.TestCase):
    def test_jsn_warning_matches_export_and_clears(self):
        rows = pd.DataFrame({"Captain":["JSN"]*12+["QB"]*8,
                             "Flex1":["QB"]*12+["JSN"]*8})
        controls = {"JSN":{"Captain Max %":30,"Flex Max %":40,"Max Exposure %":60}}
        result = exposure_status(rows, ["Captain","Flex1"], "Captain", controls).set_index("Player")
        self.assertIn("Captain: 12 selected, max 6", result.loc["JSN","Limit status"])
        self.assertIn("Overall: 20 selected, max 12", result.loc["JSN","Limit status"])
        self.assertEqual(result.loc["JSN","Captain Max %"],30)
        with self.assertRaises(ValueError):
            validate_exposure_limits(rows, ["Captain","Flex1"], controls)
        clear = exposure_status(rows, ["Captain","Flex1"], "Captain", {})
        self.assertTrue(clear["Limit status"].eq("").all())

    def test_mvp_flex_rounding_and_empty(self):
        rows = pd.DataFrame({"MVP":["A","B","C"],"FLEX1":["B","A","A"]})
        controls = {"A":{"Flex Max %":50}}
        result = exposure_status(rows, ["MVP","FLEX1"], "MVP", controls).set_index("Player")
        self.assertEqual(result.loc["A","Limit status"],"❌ FLEX: 2 selected, max 1")
        self.assertTrue(exposure_status(pd.DataFrame(),["MVP"],"MVP",{}).empty)
