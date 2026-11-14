import unittest
from simmah_nba_role_prior_offline import training_examples,current_prior,preceding,role_from_history

class RolePriorTests(unittest.TestCase):
    def rows(self):
        return [dict(key=['a','MIL'],date=f'2026-10-{i:02}',game_id=str(i),game_started_at=f'2026-10-{i:02}T20:00Z',completed_at=f'2026-10-{i:02}T23:00Z',started=True,minutes=30) for i in range(1,9)]
    def test_target_and_future_outcomes_cannot_change_prior(self):
        rows=self.rows();examples=training_examples(rows)
        before=current_prior(rows,examples,['a','MIL'],'2026-10-08','2026-10-08T18:00Z',minimum_training_examples=2)
        rows[-1]['minutes']=48;rows[-1]['started']=False
        after=current_prior(rows,training_examples(rows),['a','MIL'],'2026-10-08','2026-10-08T18:00Z',minimum_training_examples=2)
        self.assertEqual(before,after)
    def test_unknown_player_gets_no_numeric_prior(self):
        r=current_prior(self.rows(),training_examples(self.rows()),['new','MIL'],'2026-11-01','2026-11-01T18:00Z')
        self.assertFalse(r['supported']);self.assertNotIn('minutes',r)
    def test_role_feature_precedes_label_game(self):
        rows=self.rows();examples=training_examples(rows)
        self.assertEqual(examples[0]['game_id'],'4')
        self.assertEqual(examples[0]['role_published_at'],'2026-10-03T23:00Z')
    def test_same_day_history_excluded(self):
        self.assertEqual(len(preceding(self.rows(),['a','MIL'],'2026-10-04','2026-10-04T22:00Z')),3)
    def test_missing_games_do_not_become_nonstarts(self):
        rows=self.rows()[::3]
        self.assertEqual(role_from_history(rows)['trailing_starter_rate'],1)
    def test_insufficient_role_training_has_no_numeric_prior(self):
        r=current_prior(self.rows(),training_examples(self.rows()),['a','MIL'],'2026-11-01','2026-11-01T18:00Z')
        self.assertFalse(r['supported']);self.assertNotIn('minutes',r)

if __name__=='__main__':unittest.main()
