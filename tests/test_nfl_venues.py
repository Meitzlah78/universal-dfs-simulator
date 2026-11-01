import unittest
from simmah_nfl_venues import venue_location, EVERBANK


class NflVenueTests(unittest.TestCase):
    def test_espn_jacksonville_venue_id_and_aliases(self):
        self.assertEqual(venue_location({'id':'3712','fullName':'EverBank Stadium','indoor':False}),EVERBANK)
        for name in ('EverBank Stadium','EverBank Field','TIAA Bank Field'):
            self.assertEqual(venue_location({'fullName':name}),EVERBANK)

    def test_other_venues_and_unknown_locations_keep_existing_behavior(self):
        self.assertEqual(venue_location({'fullName':'Lumen Field'}),(47.5952,-122.3316,False))
        self.assertEqual(venue_location({'fullName':'Indoor venue','indoor':True}),(None,None,True))
        self.assertIsNone(venue_location({'fullName':'Wembley Stadium','address':{'country':'England'}}))
        self.assertIsNone(venue_location({'fullName':'Unknown stadium','homeTeam':'JAX'}))
