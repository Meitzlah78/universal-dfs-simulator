import unittest
import pandas as pd
from simmah_nfl_outcomes import archive_completed_scores


class CompletedOutcomeTests(unittest.TestCase):
    def test_explicit_zero_negative_dst_missing_and_duplicate(self):
        state={};frame=pd.DataFrame({'Player':['Kicker','Defense','Missing','Kicker'],'FPTS':[0,-2,None,0]})
        profiles=[{'format':'DK_SHOWDOWN'}]
        report=archive_completed_scores(state,[frame],profiles,'raw','standings.csv','2026-10-19')
        self.assertEqual(report['player_scores_added'],2)
        snapshot=next(iter(state['nfl_completed_player_results'].values()))
        self.assertEqual(sorted(p['Actual Points'] for p in snapshot['players']),[-2,0])
        self.assertEqual(archive_completed_scores(state,[frame],profiles,'zip','standings.zip','2026-10-19')['snapshots_added'],0)

    def test_conflict_fails_without_saving(self):
        state={};frame=pd.DataFrame({'Player':['A','A'],'FPTS':[1,2]})
        with self.assertRaises(ValueError):archive_completed_scores(state,[frame],[{'format':'FD_FULL'}],'a','bad.csv')
        self.assertFalse(state['nfl_completed_player_results'])

    def test_no_score_column_never_invents_actuals(self):
        state={};frame=pd.DataFrame({'Player':['A'],'Points':[100]})
        report=archive_completed_scores(state,[frame],[{'format':'DK_CLASSIC'}],'a','standings.csv')
        self.assertEqual(report['player_scores_added'],0)
