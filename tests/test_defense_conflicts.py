import unittest
from simmah_candidates import offense_vs_defense_allowed


class DefenseConflictTest(unittest.TestCase):
    def test_all_offensive_positions_are_blocked_against_defense(self):
        for pos in ["QB","RB","WR","TE","K"]:
            for defense_pos in ["D","DST","DEF"]:
                lookup={"Defense":{"Position":defense_pos,"Team":"PHI","Opponent":"CAR"},
                        "Player":{"Position":pos,"Team":"CAR","Opponent":"PHI"}}
                self.assertFalse(offense_vs_defense_allowed({"D":"Defense","FLEX":"Player"},lookup))
                lookup["Player"].update(Team="PHI",Opponent="CAR")
                self.assertTrue(offense_vs_defense_allowed({"D":"Defense","FLEX":"Player"},lookup))

    def test_aliases_and_either_side_of_matchup(self):
        lookup={"D":{"Position":"DST","Team":"LA"},
                "P":{"Position":"WR","Team":"ARI","Opponent":"LAR"}}
        self.assertFalse(offense_vs_defense_allowed({"DST":"D","WR":"P"},lookup))
        lookup["D"].update(Team="",Opponent="WSH")
        lookup["P"].update(Team="WAS",Opponent="")
        self.assertFalse(offense_vs_defense_allowed({"DST":"D","WR":"P"},lookup))

    def test_no_defense_and_unrelated_games(self):
        lookup={"D":{"Position":"D","Team":"BUF","Opponent":"LV"},
                "P":{"Position":"QB","Team":"CAR","Opponent":"PHI"}}
        self.assertTrue(offense_vs_defense_allowed({"D":"D","QB":"P"},lookup))
        self.assertTrue(offense_vs_defense_allowed({"QB":"P"},lookup))
