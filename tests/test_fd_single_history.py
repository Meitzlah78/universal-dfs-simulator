import unittest
import pandas as pd
from simmah_contest_history import ingest_frames,parse_lineups

class FDSingleHistoryTest(unittest.TestCase):
    def fixture(self):
        players=['Alpha','Bravo','Charlie','Delta','Echo','Kicker']
        lineup=', '.join(f'{pos} {name} (123-{i})' for i,(pos,name) in enumerate(zip(['WR','QB','RB','WR','TE','K'],players)))
        return pd.DataFrame({'Rank':[1]*6,'EntryId':[100]*6,'Lineup':[lineup]*6,
            'Points':[24.]*6,'Player':[f'{n} (123-{i})' for i,n in enumerate(players)],'FPTS':[6,5,4,3,2,1]})
    def test_positional_export_verifies_first_mvp_and_includes_kicker(self):
        f=self.fixture();self.assertEqual(len(parse_lineups(f)[0]),6)
        p=ingest_frames([f],'fixture')[0]
        self.assertEqual(p['format'],'FD_SINGLE');self.assertEqual(p['roster_size'],6)
        self.assertEqual(p['features']['captain_popularity']['mean'],100)
    def test_wrong_multiplier_and_missing_scores_rejected(self):
        f=self.fixture();f['Points']=21
        with self.assertRaisesRegex(ValueError,'reconcile'):ingest_frames([f],'fixture')
        with self.assertRaises(ValueError):ingest_frames([self.fixture().drop(columns='FPTS')],'fixture')
    def test_full_roster_selection_does_not_reinterpret_single(self):
        with self.assertRaises(ValueError):ingest_frames([self.fixture()],'fixture',platform='FanDuel',mode='Full Roster')
