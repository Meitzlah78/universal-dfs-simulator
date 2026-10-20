import tempfile
import unittest
from unittest.mock import patch
from scripts import nba_history_check as audit
import test_nba_fit
import test_nba_roles


class HistoryAuditTests(unittest.TestCase):
    def test_bad_game_excluded_and_holdout_date_kept_separate(self):
        def game(eid, before):
            if eid == 'bad':
                raise ValueError('score mismatch')
            day = '2026-04-01' if int(eid) < 32 else '2026-04-02'
            g = test_nba_fit.NBAFitTests().game(day, eid)
            g['boxscore']['players']=test_nba_roles.game()['boxscore']['players']
            g.update(home_score=100, away_score=100)
            return g
        with tempfile.TemporaryDirectory() as cache, \
             patch.object(audit, 'completed_games', return_value=[str(i) for i in range(40)]+['bad']), \
             patch.object(audit, 'download_game', side_effect=game), \
             patch.object(audit, 'reconstruct', return_value=[{'points':200,'usable':True}]), \
             patch.object(audit, 'reconstruct_rotations', return_value={'complete':True,'issues':[]}):
            report = audit.run('2026-04-01','2026-04-02','2026-10-20',cache,41,8)
        self.assertEqual(report['training_games'],32)
        self.assertEqual(report['holdout_games'],8)
        self.assertEqual(report['rejected_games'],[{'event_id':'bad','reason':'score mismatch'}])
        self.assertTrue(all(g['date'] < report['holdout_start']
                            for g in report['audits'] if g['split']=='training'))

    def test_invalid_split_rejected(self):
        with self.assertRaises(ValueError):
            audit.run('2026-04-01','2026-04-02','2026-10-20','unused',10,0)
