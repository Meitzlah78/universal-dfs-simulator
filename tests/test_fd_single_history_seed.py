import json,unittest
from pathlib import Path
from simmah_contest_history import load_store,matching_profiles

class FDSingleHistorySeedTests(unittest.TestCase):
    def test_completed_hail_mary_profile_is_scoped_and_anonymous(self):
        store=load_store(Path('data/field_history_seed.json'))
        profile=next(p for p in store['contests'] if p.get('source_contest_id')=='135541-281148543')
        self.assertEqual(profile['format'],'FD_SINGLE')
        self.assertEqual(profile['lineups'],88087)
        self.assertEqual(profile['field_entries'],88714)
        self.assertEqual(profile['blank_lineups_excluded'],627)
        self.assertEqual(profile['unique_lineups'],10440)
        self.assertEqual(profile['features']['captain_popularity']['count'],88087)
        self.assertIn(profile,matching_profiles(store,'FanDuel','Single Game',fee=.25,roster_size=6,game_count=1))
        self.assertNotIn('meitzlah78',json.dumps(profile).lower())
        self.assertNotIn('scores',profile)
