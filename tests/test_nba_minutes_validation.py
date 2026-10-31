import unittest
import pandas as pd
from simmah_nba_minutes_validation import freeze_minutes,grade_minutes

class MinutesValidationTests(unittest.TestCase):
    def test_freeze_only_pregame_and_never_missing_as_zero(self):
        pool=pd.DataFrame({'Player ID':['1','2','3','4'],'Projected Minutes':[30,0,None,20],
            'GameStart':['2026-10-20T23:00Z']*3+['2026-10-20T18:00Z']})
        snap=freeze_minutes(pool,'DraftKings','2026-10-20T19:00Z')
        self.assertEqual([p['Player ID'] for p in snap['players']],['1','2'])
        later=freeze_minutes(pool,'DraftKings','2026-10-20T20:00Z')
        self.assertEqual(snap['signature'],later['signature'])
        self.assertIsNone(freeze_minutes(pool,'DraftKings','2026-10-21T00:00Z'))
        result=grade_minutes(snap,pd.DataFrame({'Player ID':['1'],'Minutes':[0]}))
        self.assertEqual(result['matched'],1);self.assertEqual(result['unmatched'],1)
        self.assertEqual(result['verified_zero_minutes'],1);self.assertEqual(result['mae'],30)
        self.assertTrue(pd.isna(result['report'].iloc[1]['Error']))
    def test_bad_actuals_rejected(self):
        snap={'players':[{'Player ID':'1','Projected Minutes':30}]}
        for minutes in ([None],[-1],[float('inf')]):
            with self.assertRaises(ValueError):grade_minutes(snap,pd.DataFrame({'Player ID':['1'],'Minutes':minutes}))
